const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export interface DeviceItem {
  id: string
  name: string
  location: string
  online: boolean
  temperature: number
  humidity: number
  luminosity: number
}

export interface SensorRange {
  min: number
  max: number
}

export interface TriggerConfig {
  temperature: SensorRange
  humidity: SensorRange
  luminosity: SensorRange
}

export interface CurrentReading {
  device_id: string
  entity_urn: string
  timestamp: string
  temperature: number
  humidity: number
  luminosity: number
  online: boolean
  status: string
  alerts: {
    alertTemp?: boolean
    alertHum?: boolean
    alertLum?: boolean
  }
}

export interface HistoryPoint {
  time: string
  value: number
}

export interface HistorySeries {
  temperature: HistoryPoint[]
  humidity: HistoryPoint[]
  luminosity: HistoryPoint[]
}

export interface HistoryResponse {
  device_id: string
  period: string
  history: HistorySeries
  source: string
}

export interface EnvironmentalIncident {
  id: number
  type: 'temperature' | 'humidity' | 'luminosity'
  direction: 'high' | 'low'
  title: string
  startedAt: string
  endedAt: string
  duration: string
  peakValue: string
  description: string
  active?: boolean
}

export interface WineMemoryData {
  device_id: string
  totalIncidents: number
  exposureTime: string
  lastIncident: string
  stability: number | null
  incidents: EnvironmentalIncident[]
  sampleCount: number
  source: 'recorded' | 'estimated'
}

export interface AlertItem {
  id: number
  sensor: string
  message: string
  value: string
  time: string
  active: boolean
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE.replace(/\/+$/, '')}/${endpoint.replace(/^\/+/, '')}`
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  }

  const response = await fetch(url, { ...options, headers })

  if (!response.ok) {
    let errorDetail = `Erro HTTP ${response.status}: ${response.statusText}`
    try {
      const errorJson = await response.json()
      if (errorJson.detail) {
        errorDetail = errorJson.detail
      }
    } catch {
      // ignore
    }
    throw new Error(errorDetail)
  }

  return response.json() as Promise<T>
}

export const api = {
  getDevices: () => request<{ items: DeviceItem[]; total: number }>('/devices'),

  createDevice: (payload: { device_id: string; name: string; location: string }) =>
    request<DeviceItem>('/devices', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  deleteDevice: (device_id: string) =>
    request<{ device_id: string; deleted: boolean }>(`/devices/${encodeURIComponent(device_id)}`, {
      method: 'DELETE',
    }),

  getCurrentReading: (device_id: string) =>
    request<CurrentReading>(`/devices/${encodeURIComponent(device_id)}/current`),

  getHistory: (device_id: string, period: '24h' | '7d' | '30d') =>
    request<HistoryResponse>(`/devices/${encodeURIComponent(device_id)}/history?period=${period}`),

  getTriggers: (device_id: string) =>
    request<{ device_id: string; triggers: TriggerConfig }>(`/devices/${encodeURIComponent(device_id)}/triggers`),

  updateTriggers: (device_id: string, triggers: TriggerConfig) =>
    request<{ device_id: string; triggers: TriggerConfig; message: string }>(
      `/devices/${encodeURIComponent(device_id)}/triggers`,
      {
        method: 'PUT',
        body: JSON.stringify(triggers),
      },
    ),

  getWineMemory: (device_id: string) =>
    request<WineMemoryData>(`/devices/${encodeURIComponent(device_id)}/wine-memory`),

  getAlerts: (device_id: string) =>
    request<{ device_id: string; alerts: AlertItem[] }>(`/devices/${encodeURIComponent(device_id)}/alerts`),

  startMonitoring: (device_id: string) =>
    request<{ device_id: string; monitoring: boolean }>(
      `/devices/${encodeURIComponent(device_id)}/monitoring/start`,
      { method: 'POST' },
    ),

  stopMonitoring: (device_id: string) =>
    request<{ device_id: string; monitoring: boolean }>(
      `/devices/${encodeURIComponent(device_id)}/monitoring/stop`,
      { method: 'POST' },
    ),

  getMonitoringStatus: (device_id: string) =>
    request<{ device_id: string; is_active: boolean; active_alerts: Record<string, boolean> }>(
      `/devices/${encodeURIComponent(device_id)}/monitoring`,
    ),

  getFiwareHealth: () =>
    request<Record<string, unknown>>('/health/fiware'),
}

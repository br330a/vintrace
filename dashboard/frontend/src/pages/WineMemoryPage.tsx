import {
  useEffect,
  useState,
} from 'react'

import {
  AlertCircle,
  Clock3,
  Droplets,
  History,
  Lightbulb,
  Loader2,
  RefreshCw,
  ShieldCheck,
  Thermometer,
  TriangleAlert,
} from 'lucide-react'

import {
  api,
  type DeviceItem,
  type EnvironmentalIncident,
  type WineMemoryData,
} from '../services/api'

function WineMemoryPage() {
  const [devices, setDevices] =
    useState<DeviceItem[]>([])

  const [deviceId, setDeviceId] =
    useState('vintrace001')

  const [memory, setMemory] =
    useState<WineMemoryData | null>(
      null,
    )

  const [loading, setLoading] =
    useState(false)

  const [error, setError] =
    useState('')

  const [refreshKey, setRefreshKey] =
    useState(0)

  useEffect(() => {
    const timeout =
      setTimeout(() => {
        void (async () => {
          try {
            const res =
              await api.getDevices()

            setDevices(
              res.items ?? [],
            )

            if (
              res.items &&
              res.items.length >
                0
            ) {
              setDeviceId(
                (currentId) =>
                  res.items.some(
                    (device) =>
                      device.id ===
                      currentId,
                  )
                    ? currentId
                    : res.items[0]
                        .id,
              )
            }
          } catch (
            err: unknown
          ) {
            const msg =
              err instanceof Error
                ? err.message
                : 'Falha ao carregar dispositivos'

            setDevices([])
            setError(msg)
          }
        })()
      }, 0)

    return () =>
      clearTimeout(timeout)
  }, [])

  useEffect(() => {
    if (!deviceId) {
      return
    }

    let cancelled = false

    const loadWineMemory = async (showLoading: boolean) => {
      if (showLoading && !cancelled) {
        setLoading(true)
      }

      try {
        const data = await api.getWineMemory(deviceId)
        if (!cancelled) {
          setMemory(data)
          setError('')
        }
      } catch (err: unknown) {
        if (!cancelled) {
          const msg = err instanceof Error
            ? err.message
            : 'Falha ao consultar histórico do STH-Comet'
          setError(msg)
          setMemory(null)
        }
      } finally {
        if (!cancelled && showLoading) {
          setLoading(false)
        }
      }
    }

    // Revalida a cada 30 s; não é mais necessário sair da tela.
    const timeout = setTimeout(() => {
      void loadWineMemory(true)
    }, 0)
    const interval = setInterval(() => {
      void loadWineMemory(false)
    }, 30000)

    return () => {
      cancelled = true
      clearTimeout(timeout)
      clearInterval(interval)
    }
  }, [deviceId, refreshKey])

  function getIncidentIcon(
    type:
      EnvironmentalIncident['type'],
  ) {
    if (
      type ===
      'temperature'
    ) {
      return Thermometer
    }

    if (
      type === 'humidity'
    ) {
      return Droplets
    }

    return Lightbulb
  }

  return (
    <div>
      <div>
        <p className="text-sm font-medium text-amber-400">
          Passaporte Ambiental
        </p>

        <h1 className="mt-1 text-3xl font-semibold">
          Wine Memory
        </h1>

        <p className="mt-2 max-w-2xl text-zinc-400">
          Acompanhe os incidentes ambientais registrados e a estabilidade das medições históricas.
        </p>
      </div>

      <div className="mt-8 flex flex-wrap items-end gap-4">
        <div>
          <label className="text-sm text-zinc-400">
          Dispositivo
        </label>

        <select
          value={deviceId}
          onChange={(event) =>
            setDeviceId(
              event.target.value,
            )
          }
          className="mt-2 w-full rounded-xl border border-zinc-700 bg-zinc-900 px-4 py-3 text-sm outline-none transition focus:border-amber-400 sm:max-w-sm"
        >
          {devices.length >
          0 ? (
            devices.map(
              (device) => (
                <option
                  key={
                    device.id
                  }
                  value={
                    device.id
                  }
                >
                  {
                    device.name
                  }{' '}
                  —{' '}
                  {
                    device.id
                  }
                </option>
              ),
            )
          ) : (
            <option value="">
              Nenhum dispositivo disponível
            </option>
          )}
        </select>
        </div>
        <button
          type="button"
          onClick={() => setRefreshKey((value) => value + 1)}
          className="inline-flex items-center gap-2 rounded-xl border border-zinc-700 px-4 py-3 text-sm text-zinc-200 transition hover:border-amber-400"
          title="Atualizar Wine Memory"
        >
          <RefreshCw size={16} /> Atualizar
        </button>
      </div>

      {error && (
        <div className="mt-4 flex items-center gap-3 rounded-xl border border-amber-900/50 bg-amber-950/20 p-4 text-xs text-amber-300">
          <AlertCircle
            size={16}
            className="shrink-0"
          />

          <span>
            Falha ao consultar o Wine Memory ({error}).
          </span>
        </div>
      )}

      {loading ? (
        <div className="mt-8 flex items-center justify-center p-12 text-zinc-500">
          <Loader2
            className="mr-2 animate-spin"
            size={24}
          />

          <span>
            Calculando Passaporte Ambiental a partir do STH-Comet...
          </span>
        </div>
      ) : memory ? (
        <>
          <p className="mt-5 text-sm text-zinc-400">
            {memory.source === 'recorded'
              ? 'Ocorrências salvas no FIWARE no momento do alerta. Alterar os triggers depois não apaga esses registros.'
              : 'Estimativa calculada com o histórico do STH-Comet e os triggers atuais. Alertas anteriores à ativação do registro persistente podem ser reavaliados.'}
            {' '}Amostras consultadas: {memory.sampleCount}.
          </p>
          <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
              <div className="flex items-center justify-between">
                <p className="text-sm text-zinc-400">
                  Incidentes
                </p>

                <TriangleAlert
                  size={20}
                  className="text-amber-400"
                />
              </div>

              <p className="mt-3 text-3xl font-semibold">
                {
                  memory.totalIncidents
                }
              </p>

              <p className="mt-2 text-sm text-zinc-500">
                Ocorrências registradas
              </p>
            </div>

            <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
              <div className="flex items-center justify-between">
                <p className="text-sm text-zinc-400">
                  Tempo de exposição
                </p>

                <Clock3
                  size={20}
                  className="text-amber-400"
                />
              </div>

              <p className="mt-3 text-3xl font-semibold">
                {
                  memory.exposureTime
                }
              </p>

              <p className="mt-2 text-sm text-zinc-500">
                Fora das faixas configuradas
              </p>
            </div>

            <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
              <div className="flex items-center justify-between">
                <p className="text-sm text-zinc-400">
                  Última ocorrência
                </p>

                <History
                  size={20}
                  className="text-amber-400"
                />
              </div>

              <p className="mt-3 text-xl font-semibold">
                {
                  memory.lastIncident
                }
              </p>

              <p className="mt-2 text-sm text-zinc-500">
                Registro mais recente
              </p>
            </div>

            <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
              <div className="flex items-center justify-between">
                <p className="text-sm text-zinc-400">
                  Estabilidade
                </p>

                <ShieldCheck
                  size={20}
                  className="text-emerald-400"
                />
              </div>

              <p className="mt-3 text-3xl font-semibold">
                {memory.stability === null
                  ? '—'
                  : `${memory.stability.toLocaleString('pt-BR', {
                      maximumFractionDigits: memory.stability > 99.9 ? 6 : 1,
                    })}%`}
              </p>

              <p className="mt-2 text-sm text-zinc-500">
                {memory.stability === null
                  ? 'Sem histórico suficiente para calcular'
                  : memory.source === 'recorded'
                    ? 'Tempo observado sem incidentes registrados'
                    : 'Amostras dentro dos limites atuais'}
              </p>
            </div>
          </div>

          <div className="mt-6 rounded-2xl border border-zinc-800 bg-zinc-900">
            <div className="border-b border-zinc-800 p-5">
              <h2 className="font-semibold">
                Histórico de ocorrências ambientais
              </h2>

              <p className="mt-1 text-sm text-zinc-500">
                Eventos gerados pelo confronto dos pontos STH-Comet com os limites cadastrados.
              </p>
            </div>

            {memory.incidents
              .length === 0 ? (
              <div className="p-8 text-center text-sm text-zinc-500">
                {memory.sampleCount === 0
                  ? 'Ainda não há medições suficientes no STH-Comet. Isso não significa estabilidade de 100%.'
                  : 'Nenhum incidente identificado nos dados disponíveis. A ausência de ocorrências não garante estabilidade fora do período observado.'}
              </div>
            ) : (
              <div className="divide-y divide-zinc-800">
                {memory.incidents.map(
                  (incident) => {
                    const Icon =
                      getIncidentIcon(
                        incident.type,
                      )

                    return (
                      <div
                        key={
                          incident.id
                        }
                        className="p-5"
                      >
                        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                          <div className="flex items-start gap-3">
                            <div className="rounded-xl bg-red-950 p-2.5 text-red-400">
                              <Icon
                                size={
                                  20
                                }
                              />
                            </div>

                            <div>
                              <h3 className="font-medium text-zinc-200">
                                {
                                  incident.title
                                }
                              </h3>

                              <p className="mt-1 text-sm leading-6 text-zinc-500">
                                {
                                  incident.description
                                }
                              </p>
                            </div>
                          </div>

                          <div className="shrink-0 sm:text-right">
                            <p className="font-medium text-red-400">
                              {
                                incident.peakValue
                              }
                            </p>

                            <p className="mt-1 text-xs text-zinc-500">
                              {memory.source === 'recorded'
                                ? 'Leitura no início do alerta'
                                : 'Pico registrado no histórico'}
                            </p>
                          </div>
                        </div>

                        <div className="mt-5 grid grid-cols-1 gap-3 rounded-xl bg-zinc-950 p-4 text-sm sm:grid-cols-3">
                          <div>
                            <p className="text-xs text-zinc-600">
                              Início
                            </p>

                            <p className="mt-1 text-zinc-300">
                              {
                                incident.startedAt
                              }
                            </p>
                          </div>

                          <div>
                            <p className="text-xs text-zinc-600">
                              Normalização
                            </p>

                            <p className="mt-1 text-zinc-300">
                              {
                                incident.endedAt
                              }
                            </p>
                          </div>

                          <div>
                            <p className="text-xs text-zinc-600">
                              Duração
                            </p>

                            <p className="mt-1 text-zinc-300">
                              {
                                incident.duration
                              }
                            </p>
                          </div>
                        </div>
                      </div>
                    )
                  },
                )}
              </div>
            )}
          </div>
        </>
      ) : (
        <div className="mt-8 rounded-2xl border border-dashed border-zinc-800 p-8 text-center text-sm text-zinc-500">
          Nenhum dado do Wine Memory disponível.
        </div>
      )}
    </div>
  )
}

export default WineMemoryPage
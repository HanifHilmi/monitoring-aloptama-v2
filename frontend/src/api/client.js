const BASE = '/api/v1'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API ${res.status}: ${body}`)
  }
  return res.json()
}

export const api = {
  // Real-time status
  getStatusOverview: () => request('/status/overview'),
  getCdpConnectivity: (cdpId, hours = 24) =>
    request(`/status/cdp/${cdpId}/connectivity?hours=${hours}`),

  // Telemetry
  getTelemetry: (siteSlug, sensorCode, range = '24h', downsample = 1000) =>
    request(
      `/telemetry/${siteSlug}/${sensorCode}?range=${range}&downsample=${downsample}`,
    ),

  // SLA / OLA
  getSlaOlaSummary: (range = '30d') =>
    request(`/sla-ola/summary?range=${range}`),
  getDailyRollup: (scope, entityType, entityId, days = 30) =>
    request(
      `/sla-ola/daily?scope=${scope}&entity_type=${entityType}&entity_id=${entityId}&days=${days}`,
    ),
  getDowntimeEvents: (scope = 'ola', siteSlug, sensorCode, limit = 100) => {
    const params = new URLSearchParams({ scope, limit })
    if (siteSlug) params.set('site_slug', siteSlug)
    if (sensorCode) params.set('sensor_code', sensorCode)
    return request(`/sla-ola/events?${params.toString()}`)
  },

  // System health / connectivity
  getSystemHealth: () => request('/system/health'),
}

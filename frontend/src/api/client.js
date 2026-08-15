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

  // Wide awos_metrics: fetch several metric columns in one call.
  getWideTelemetry: (siteSlug, aliases = [], win = null, range = 'today') => {
    const q = new URLSearchParams({ range })
    if (aliases.length) q.set('metrics', aliases.join(','))
    if (win?.start) q.set('start', win.start)
    if (win?.end) q.set('end', win.end)
    return request(`/telemetry/${siteSlug}?${q.toString()}`)
  },
  // SLA / OLA (corrected semantics)
  getAvailability: (range = 'month', win = null) => {
    const q = new URLSearchParams({ range })
    if (win?.start) q.set('start', win.start)
    if (win?.end) q.set('end', win.end)
    return request(`/sla-ola/summary?${q.toString()}`)
  },
  getAvailabilityHistory: (bucket = 'daily', span = 'month', win = null) => {
    const q = new URLSearchParams({ bucket, span })
    if (win?.start) q.set('start', win.start)
    if (win?.end) q.set('end', win.end)
    return request(`/sla-ola/history?${q.toString()}`)
  },
  // Downtime map (yearly calendar heatmap)
  getDowntimeMap: (year) => request(`/sla-ola/downtime-map?year=${year}`),

  // System health / connectivity
  getSystemHealth: () => request('/system/health'),

  // Manual backfill (SSE progress lines)
  backfillCdp: async (onLine) => {
    const res = await fetch('/api/v1/backfill/cdp', { method: 'POST' })
    if (!res.ok || !res.body) throw new Error(`backfill failed: ${res.status}`)
    const reader = res.body.getReader()
    const dec = new TextDecoder()
    let buf = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const parts = buf.split('\n\n')
      buf = parts.pop() || ''
      for (const part of parts) {
        const line = part.replace(/^data:\s*/, '').trim()
        if (line) onLine(line)
      }
    }
  },
  backfillAll: async (onLine, onJobId) => {
    // Combined CDP+DCP backfill job (server-side, survives refresh).
    const res = await fetch('/api/v1/backfill/all/start', { method: 'POST' })
    if (!res.ok) {
      const t = await res.text().catch(() => '')
      throw new Error('backfill start failed: ' + res.status + (t ? ' ' + t.trim().slice(0, 100) : ''))
    }
    const start = await res.json()
    if (!start.ok) throw new Error(start.error || 'backfill start failed')
    if (onJobId) onJobId(start.job_id)
    await api.resumeBackfill(start.job_id, onLine)
  },
  // Reconnect to an in-flight job: replays captured log lines then tails live.
  resumeBackfill: async (jobId, onLine) => {
    const res = await fetch(`/api/v1/backfill/job/${jobId}/stream`)
    if (!res.ok || !res.body) throw new Error(`resume failed: ${res.status}`)
    const reader = res.body.getReader()
    const dec = new TextDecoder()
    let buf = ''
    let ended = false
    for (;;) {
      let r
      try {
        r = await reader.read()
      } catch {
        // Uvicorn/nginx/browser can abort the long SSE stream mid-frame;
        // treat as end-of-stream (job data already drained) rather than an error.
        ended = true
        break
      }
      const { done, value } = r
      if (done) break
      buf += dec.decode(value, { stream: true })
      const parts = buf.split('\n\n')
      buf = parts.pop() || ''
      for (const part of parts) {
        const line = part.replace(/^data:\s*/, '').trim()
        if (line) {
          onLine(line)
          if (/^JOB (DONE|ERROR)/.test(line)) ended = true
        }
      }
    }
    if (!ended && buf.trim()) onLine(buf.replace(/^data:\s*/, '').trim())
  },
  backfillDcp: async (onLine) => {
    const res = await fetch('/api/v1/backfill/dcp', { method: 'POST' })
    if (!res.ok || !res.body) throw new Error(`backfill failed: ${res.status}`)
    const reader = res.body.getReader()
    const dec = new TextDecoder()
    let buf = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const parts = buf.split('\n\n')
      buf = parts.pop() || ''
      for (const part of parts) {
        const line = part.replace(/^data:\s*/, '').trim()
        if (line) onLine(line)
      }
    }
  },
}
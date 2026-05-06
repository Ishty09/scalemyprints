/**
 * Cloudflare Worker relay for UK trademark APIs.
 *
 * UKIPO and TMview block DigitalOcean IPs. This edge route makes the
 * outbound fetch() from Cloudflare's network, bypassing the block.
 *
 * Called by the Python backend (not the browser). Protected by
 * X-Relay-Secret matching INTERNAL_API_SECRET.
 */

export const runtime = 'edge'

const BROWSER_UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'

export async function GET(request: Request): Promise<Response> {
  // Auth
  const secret = request.headers.get('x-relay-secret')
  if (!secret || secret !== process.env.INTERNAL_API_SECRET) {
    return Response.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const { searchParams } = new URL(request.url)
  const target = searchParams.get('url')
  if (!target) {
    return Response.json({ error: 'Missing url param' }, { status: 400 })
  }

  // Sanity-check: only allow trademark registry domains
  const allowed = ['trademarks.ipo.gov.uk', 'www.tmdn.org', 'tmdn.org']
  const hostname = new URL(target).hostname
  if (!allowed.includes(hostname)) {
    return Response.json({ error: `Domain not allowed: ${hostname}` }, { status: 403 })
  }

  try {
    const upstream = await fetch(target, {
      headers: {
        'User-Agent': BROWSER_UA,
        Accept: 'application/json, text/plain, */*',
        'Accept-Language': 'en-GB,en;q=0.9',
        'Cache-Control': 'no-cache',
      },
      // CF Workers respect redirect by default
    })

    const body = await upstream.arrayBuffer()
    return new Response(body, {
      status: upstream.status,
      headers: {
        'content-type': upstream.headers.get('content-type') ?? 'application/json',
      },
    })
  } catch (err) {
    return Response.json({ error: String(err) }, { status: 502 })
  }
}

/**
 * Cloudflare Worker relay for UK trademark APIs.
 *
 * UKIPO and TMview block DigitalOcean IPs. This edge route makes the
 * outbound fetch() from Cloudflare's network, bypassing the block.
 *
 * Called by the Python backend (not the browser). Protected by
 * X-Relay-Secret matching INTERNAL_API_SECRET.
 */

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

  // Build browser-like headers. For tmdn.org, mimic a same-origin XHR from
  // the TMView portal so Akamai bot detection lets us through.
  const browserHeaders: Record<string, string> = {
    'User-Agent': BROWSER_UA,
    Accept: 'application/json, text/plain, */*',
    'Accept-Language': 'en-GB,en;q=0.9',
    'Cache-Control': 'no-cache',
    'Sec-Ch-Ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'X-Requested-With': 'XMLHttpRequest',
  }
  if (hostname === 'www.tmdn.org' || hostname === 'tmdn.org') {
    browserHeaders.Origin = 'https://www.tmdn.org'
    browserHeaders.Referer = 'https://www.tmdn.org/tmview/welcome'
  }

  try {
    const upstream = await fetch(target, {
      headers: browserHeaders,
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

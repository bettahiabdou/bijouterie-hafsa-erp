/**
 * Cloudflare Worker: AMANA Tracking Proxy
 *
 * This worker proxies requests to the AMANA tracking API
 * and adds CORS headers to allow browser requests.
 *
 * Deploy instructions:
 * 1. Go to https://dash.cloudflare.com/
 * 2. Sign up or login (free account works)
 * 3. Go to Workers & Pages > Create application > Create Worker
 * 4. Name it "amana-proxy"
 * 5. Click "Deploy"
 * 6. Click "Edit code" and paste this entire file
 * 7. Click "Save and Deploy"
 * 8. Your proxy URL will be: https://amana-proxy.<your-subdomain>.workers.dev
 * 9. Update AMANA_PROXY_URL in Django settings with your worker URL
 */

const AMANA_API = 'https://bam-tracking.barid.ma/Tracking/Search';

// Allowed origins (add your domains here)
const ALLOWED_ORIGINS = [
  'http://localhost:8000',
  'http://127.0.0.1:8000',
  'http://89.167.27.57',
  'https://89.167.27.57',
  // Add your production domain here
];

export default {
  async fetch(request, env, ctx) {
    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
      return handleCORS(request);
    }

    const url = new URL(request.url);
    const trackingCode = url.searchParams.get('trackingCode');

    if (!trackingCode) {
      return new Response(JSON.stringify({ error: 'trackingCode parameter required' }), {
        status: 400,
        headers: corsHeaders(request),
      });
    }

    try {
      // Fetch from AMANA API
      const timestamp = Date.now();
      const amanaUrl = `${AMANA_API}?trackingCode=${encodeURIComponent(trackingCode)}&_=${timestamp}`;

      const response = await fetch(amanaUrl, {
        method: 'GET',
        headers: {
          'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
          'Accept': 'application/json, text/javascript, */*; q=0.01',
          'Accept-Language': 'fr-FR,fr;q=0.9',
          'Referer': 'https://bam-tracking.barid.ma/',
          'Origin': 'https://bam-tracking.barid.ma',
          'X-Requested-With': 'XMLHttpRequest',
        },
      });

      const data = await response.json();

      return new Response(JSON.stringify(data), {
        status: response.status,
        headers: {
          'Content-Type': 'application/json',
          ...corsHeaders(request),
        },
      });
    } catch (error) {
      return new Response(JSON.stringify({ error: error.message }), {
        status: 500,
        headers: corsHeaders(request),
      });
    }
  },
};

function corsHeaders(request) {
  const origin = request.headers.get('Origin') || '*';
  // Allow all origins for simplicity, or check against ALLOWED_ORIGINS
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, X-Requested-With',
    'Access-Control-Max-Age': '86400',
  };
}

function handleCORS(request) {
  return new Response(null, {
    status: 204,
    headers: corsHeaders(request),
  });
}

/**
 * Extension-wide configuration.
 *
 * The build mode determines the API URL — Vite injects `import.meta.env.MODE`
 * automatically. `development` builds talk to localhost; production builds
 * talk to the deployed API.
 */

const isDev = import.meta.env.MODE === 'development'

export const CONFIG = {
  apiUrl: isDev ? 'http://localhost:8000' : 'https://api.scalemyprints.com',
  marketingUrl: isDev ? 'http://localhost:3000' : 'https://scalemyprints.com',
  // Free anonymous searches per day before user must sign up
  freeSearchesPerDay: 5,
  // Cache TTL on the client to avoid hitting the API for repeated checks
  resultCacheMinutes: 60,
} as const

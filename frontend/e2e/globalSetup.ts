import type { FullConfig } from '@playwright/test'
import { createServer, type ViteDevServer } from 'vite'

let server: ViteDevServer | null = null

export default async function globalSetup(_config: FullConfig) {
  server = await createServer({
    root: process.cwd(),
    logLevel: 'error',
    server: {
      host: '127.0.0.1',
      port: 4188,
      strictPort: true,
    },
  })
  await server.listen()

  return async () => {
    await server?.close()
    server = null
  }
}

import { defineConfig, devices } from '@playwright/test'
import fs from 'node:fs'

const installedChromium = [
  process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
].find(candidate => candidate && fs.existsSync(candidate))

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: [['line']],
  use: {
    baseURL: 'http://127.0.0.1:4188',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: installedChromium
      ? { executablePath: installedChromium }
      : undefined,
    ...devices['Desktop Chrome'],
  },
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 4188 --strictPort',
    url: 'http://127.0.0.1:4188',
    env: { ...process.env },
    reuseExistingServer: false,
    timeout: 120_000,
  },
})

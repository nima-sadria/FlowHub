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
  testDir: './e2e/live',
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  outputDir: './test-results/live',
  reporter: [
    ['line'],
    ['html', { open: 'never', outputFolder: './playwright-report/live' }],
  ],
  use: {
    baseURL: process.env.FLOWHUB_E2E_BASE_URL ?? 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    launchOptions: installedChromium
      ? { executablePath: installedChromium }
      : undefined,
    ...devices['Desktop Chrome'],
  },
})

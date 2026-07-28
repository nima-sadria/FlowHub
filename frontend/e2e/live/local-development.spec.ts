import fs from 'node:fs'
import path from 'node:path'
import { expect, test } from '@playwright/test'

interface LocalCredentials {
  username: string
  password: string
}

function localCredentials(): LocalCredentials {
  const credentialsPath = path.resolve(process.cwd(), '..', '.local', 'dev', 'credentials.json')
  return JSON.parse(fs.readFileSync(credentialsPath, 'utf-8')) as LocalCredentials
}

test('local development stack supports authenticated browser debugging', async ({ page, request }) => {
  const credentials = localCredentials()
  const consoleErrors: string[] = []
  const failedRequests: string[] = []
  const apiResponses: Array<{ method: string; path: string; status: number }> = []

  page.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })
  page.on('requestfailed', browserRequest => {
    failedRequests.push(`${browserRequest.method()} ${browserRequest.url()}`)
  })
  page.on('response', response => {
    const url = new URL(response.url())
    if (url.pathname.startsWith('/api/')) {
      apiResponses.push({
        method: response.request().method(),
        path: url.pathname,
        status: response.status(),
      })
    }
  })

  const health = await request.get('/api/health')
  expect(health.status()).toBe(200)
  expect(await health.json()).toEqual(expect.objectContaining({ status: 'ok' }))

  await page.goto('/login')
  await expect(page.getByRole('heading', { name: 'Sign in to FlowHub' })).toBeVisible()
  await page.getByRole('textbox', { name: 'Email' }).fill(credentials.username)
  await page.getByRole('textbox', { name: 'Password' }).fill(credentials.password)
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page).toHaveURL(/\/home$/)
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
  const sourceProfilesResponse = page.waitForResponse(response => (
    new URL(response.url()).pathname === '/api/v2/source-profiles'
    && response.status() === 200
  ))
  await page.getByRole('link', { name: 'Sources' }).click()
  await expect(page).toHaveURL(/\/sources$/)
  await expect(page.getByRole('heading', { name: 'Sources' })).toBeVisible()
  await sourceProfilesResponse

  expect(apiResponses).toEqual(expect.arrayContaining([
    expect.objectContaining({ method: 'POST', path: '/api/auth/login', status: 200 }),
    expect.objectContaining({ method: 'GET', path: '/api/auth/me', status: 200 }),
    expect.objectContaining({ method: 'GET', path: '/api/v2/source-profiles', status: 200 }),
  ]))
  expect(failedRequests).toEqual([])
  expect(consoleErrors).toEqual([])
})

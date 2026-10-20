import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: { baseURL: 'http://127.0.0.1:5174', viewport: { width: 1440, height: 1024 }, trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  webServer: [
    { command: '../.venv/bin/python ../tests/run_settings_server.py', url: 'http://127.0.0.1:8011/openapi.json', timeout: 120000, reuseExistingServer: false },
    { command: 'npm run dev -- --host 127.0.0.1 --port 5174 --strictPort', url: 'http://127.0.0.1:5174',
      env: { API_PROXY_TARGET: 'http://127.0.0.1:8011' }, reuseExistingServer: false },
  ],
})

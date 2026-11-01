import { defineConfig, devices } from '@playwright/test';

// Playwright configuration for PayShield AI frontend.
//
// Servers are already running locally (frontend :3000, backend :8000) and are
// reused as-is: no webServer block is defined so Playwright never launches a
// duplicate server or alters their configuration.
export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : 1,
  reporter: 'html',

  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});

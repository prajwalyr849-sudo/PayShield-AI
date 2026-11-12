/**
 * PayShield AI — Product Search smoke test.
 *
 * Verifies the application renders its Product Search page in a real browser
 * against the already-running frontend (:3000) and backend (:8000).
 *
 * The Product Search page is auth-protected, so this test establishes an
 * authenticated demo session through the existing /auth/demo/login endpoint
 * (no new backend routes, no orders, no checkout, no payments). The Vite dev
 * server's spaBypass does not forward POST /auth/demo/login, so the request is
 * made directly to the backend and the session cookie is installed explicitly.
 */

import { test, expect } from '@playwright/test';

test('renders the Product Search page', async ({ page, context }) => {
  // Establish an authenticated demo session directly against the running
  // backend (:8000), which responds with a Set-Cookie for payshield_session.
  const loginResponse = await page.request.post(
    'http://127.0.0.1:8000/auth/demo/login',
    { data: {} }
  );
  expect(loginResponse.ok()).toBeTruthy();

  const setCookie = loginResponse.headers()['set-cookie'] || '';
  const match = setCookie.match(/payshield_session=([^;]+)/);
  expect(match).toBeTruthy();
  await context.addCookies([
    {
      name: 'payshield_session',
      value: match![1],
      domain: 'localhost',
      path: '/',
      httpOnly: true,
      secure: false,
    },
  ]);

  // Navigate to the Product Search route.
  await page.goto('/product-search');

  // Product Search page renders (not the sign-in wall).
  await expect(
    page.getByRole('heading', { name: /Product Search & Offer Verification/i })
  ).toBeVisible();
});

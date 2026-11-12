# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: product-search.smoke.spec.ts >> renders the Product Search page
- Location: tests\e2e\product-search.smoke.spec.ts:16:1

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByRole('heading', { name: /Product Search & Offer Verification/i })
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" getByRole('heading', { name: /Product Search & Offer Verification/i }) with timeout 5000ms
  - waiting for getByRole('heading', { name: /Product Search & Offer Verification/i })

```

```yaml
- complementary:
  - text: shield PayShieldAI Transaction Security
  - navigation:
    - text: WORKSPACE
    - button "layout Overview"
    - button "smart_toy AI Assistant"
    - button "manage_search Product Search"
  - navigation:
    - text: COMMERCE
    - button "receipt_long Transactions"
    - button "article Receipts"
  - navigation:
    - text: SECURITY
    - button "security Risk Intelligence"
    - button "tune Policies"
    - button "fingerprint Audit Logs"
  - navigation:
    - text: SYSTEM
    - button "integration_instructions Integrations"
    - button "settings Settings"
- banner:
  - button "Open command palette": search K
  - text: Product Search A Alex Smith alex@payshield.ai expand_more
- main:
  - heading "Product Search" [level=1]
  - paragraph: Search verified merchant offers. All prices and details come from the live product catalog — no simulated data.
  - text: Search
  - textbox "Search by vendor, SKU, or specification…"
  - text: Category
  - combobox:
    - option "All" [selected]
    - option "Electronics"
    - option "Software"
    - option "Services"
    - option "Other"
  - text: Verification
  - combobox:
    - option "All merchants" [selected]
    - option "Price verified only"
  - text: Sort
  - combobox:
    - option "Relevance" [selected]
    - 'option "Price: low to high"'
    - 'option "Price: high to low"'
  - button "Search"
  - heading "Results" [level=2]
  - text: 0 offers manage_search
  - heading "Search for products" [level=3]
  - paragraph: Enter a search above to browse live merchant offers from the product catalog.
```

# Test source

```ts
  1  | /**
  2  |  * PayShield AI — Product Search smoke test.
  3  |  *
  4  |  * Verifies the application renders its Product Search page in a real browser
  5  |  * against the already-running frontend (:3000) and backend (:8000).
  6  |  *
  7  |  * The Product Search page is auth-protected, so this test establishes an
  8  |  * authenticated demo session through the existing /auth/demo/login endpoint
  9  |  * (no new backend routes, no orders, no checkout, no payments). The Vite dev
  10 |  * server's spaBypass does not forward POST /auth/demo/login, so the request is
  11 |  * made directly to the backend and the session cookie is installed explicitly.
  12 |  */
  13 | 
  14 | import { test, expect } from '@playwright/test';
  15 | 
  16 | test('renders the Product Search page', async ({ page, context }) => {
  17 |   // Establish an authenticated demo session directly against the running
  18 |   // backend (:8000), which responds with a Set-Cookie for payshield_session.
  19 |   const loginResponse = await page.request.post(
  20 |     'http://127.0.0.1:8000/auth/demo/login',
  21 |     { data: {} }
  22 |   );
  23 |   expect(loginResponse.ok()).toBeTruthy();
  24 | 
  25 |   const setCookie = loginResponse.headers()['set-cookie'] || '';
  26 |   const match = setCookie.match(/payshield_session=([^;]+)/);
  27 |   expect(match).toBeTruthy();
  28 |   await context.addCookies([
  29 |     {
  30 |       name: 'payshield_session',
  31 |       value: match![1],
  32 |       domain: 'localhost',
  33 |       path: '/',
  34 |       httpOnly: true,
  35 |       secure: false,
  36 |     },
  37 |   ]);
  38 | 
  39 |   // Navigate to the Product Search route.
  40 |   await page.goto('/product-search');
  41 | 
  42 |   // Product Search page renders (not the sign-in wall).
  43 |   await expect(
  44 |     page.getByRole('heading', { name: /Product Search & Offer Verification/i })
> 45 |   ).toBeVisible();
     |     ^ Error: expect(locator).toBeVisible() failed
  46 | });
  47 | 
```
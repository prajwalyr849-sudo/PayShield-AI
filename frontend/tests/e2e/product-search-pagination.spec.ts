import { test, expect, type Page, type BrowserContext } from '@playwright/test';

/**
 * PayShield AI — Product Search pagination E2E test.
 *
 * Verifies the live Channel3 pagination flow in a real browser against the
 * already-running frontend (:3000) and backend (:8000):
 *
 *   1. authenticates via the existing /auth/demo/login endpoint
 *   2. searches for "iPhone 17" through the UI
 *   3. only clicks Load More when the first response contained a real cursor
 *   4. verifies page 2 appends results, preserves page 1, and introduces no
 *      duplicate canonical offer IDs
 *   5. changes page size and verifies a new search is issued
 *
 * The Product Search page is auth-protected. No orders, checkout, captures,
 * or refunds are involved. No application source, Vite config, or backend
 * security controls are modified.
 *
 * If results or a real cursor are unavailable, the scenario is reported as
 * NOT EXERCISED rather than fabricating results or using mock data.
 */

async function authenticateDemo({ page, context }: { page: Page; context: BrowserContext }) {
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
}

/** Read canonical offer IDs from the rendered offer cards. Each card carries
 *  its canonical provider id in the title attribute, e.g.
 *  <div title="c3_…">c3_… • category</div>. */
async function readCanonicalIds(page: Page): Promise<string[]> {
  const els = page.locator('div[title^="c3_"]');
  return els.evaluateAll((nodes) =>
    nodes.map((n) => n.getAttribute('title')).filter(Boolean) as string[]
  );
}

test('paginates search results via Load More when the provider returns a real cursor', async ({ page, context }) => {
  test.setTimeout(120000);
  await authenticateDemo({ page, context });

  await page.goto('/product-search');
  await expect(
    page.getByRole('heading', { name: /Product Search & Offer Verification/i })
  ).toBeVisible();

  // Search iPhone 17 through the UI.
  const searchInput = page.getByPlaceholder(/Search by vendor/);
  await searchInput.click({ force: true });
  await searchInput.pressSequentially('iPhone 17', { delay: 50 });
  await page.waitForTimeout(300);
  await searchInput.press('Enter');

  const offerCards = page.locator('div[title^="c3_"]');
  // Wait for search results to render after the form submission triggers
  // handleSearch -> getAssistantRecommendations -> setLiveResults.
  await expect(offerCards.first()).toBeVisible({ timeout: 60000 });

  const page1Ids = await readCanonicalIds(page);

  // The Channel3 provider may return zero results for a given query in a
  // particular run (external catalog variability). In that case the scenario
  // cannot be exercised and is reported as NOT EXERCISED rather than failing.
  if (page1Ids.length === 0) {
    test.info().annotations.push({
      type: 'comment',
      description:
        'Pagination NOT EXERCISED: the provider returned no results for ' +
        '"iPhone 17" in this run, so no products were rendered.',
    });
    return;
  }

  expect(new Set(page1Ids).size).toBe(page1Ids.length); // no duplicates on page 1

  const loadMore = page.getByRole('button', { name: /^Load more$/ });

  if (!(await loadMore.isVisible())) {
    // No cursor was returned by the provider for this query/run.
    test.info().annotations.push({
      type: 'comment',
      description:
        'Pagination NOT EXERCISED: the provider returned no next_page_token ' +
        'for "iPhone 17" in this run, so the Load More button was not rendered.',
    });
    return;
  }

  // A real next_page_token was returned: the Load More button is enabled.
  // Clicking it triggers handleSearch(searchQuery, nextPageToken) which
  // calls the same backend endpoint for page 2.
  const page2Response = page.waitForResponse((resp) => {
    try {
      const url = new URL(resp.url());
      return (
        url.pathname === '/assistant/recommendations' &&
        url.searchParams.get('page_token') !== '' &&
        resp.request().method() === 'POST'
      );
    } catch {
      return false;
    }
  });

  await loadMore.click();
  await page2Response;

  // Wait for the rendered cards to reflect the appended page-2 results.
  await page.waitForFunction(
    (prevCount) => document.querySelectorAll('div[title^="c3_"]').length > prevCount,
    page1Ids.length,
    { timeout: 30000 }
  );

  const page2Ids = await readCanonicalIds(page);

  // Page 1 results are preserved.
  for (const id of page1Ids) {
    expect(page2Ids).toContain(id);
  }

  // New results were appended.
  expect(page2Ids.length).toBeGreaterThan(page1Ids.length);

  // No duplicate canonical offer IDs across the combined result set.
  expect(new Set(page2Ids).size).toBe(page2Ids.length);
});

test('changing page size re-searches with the requested provider limit', async ({ page, context }) => {
  await authenticateDemo({ page, context });

  await page.goto('/product-search');
  await expect(
    page.getByRole('heading', { name: /Product Search & Offer Verification/i })
  ).toBeVisible();

  const searchInput = page.getByPlaceholder(/Search by vendor/);
  await searchInput.click({ force: true });
  await searchInput.pressSequentially('iPhone 17', { delay: 50 });
  await page.waitForTimeout(300);
  await searchInput.press('Enter');

  const offerCards = page.locator('div[title^="c3_"]');
  await expect(offerCards.first()).toBeVisible({ timeout: 60000 });

  const page1Ids = await readCanonicalIds(page);

  // The Channel3 provider may return zero results for a given query in a
  // particular run (external catalog variability). In that case the scenario
  // cannot be exercised and is reported as NOT EXERCISED rather than failing.
  if (page1Ids.length === 0) {
    test.info().annotations.push({
      type: 'comment',
      description:
        'Page-size change NOT EXERCISED: the provider returned no results for ' +
        '"iPhone 17" in this run, so no products were rendered.',
    });
    return;
  }

  // Change page size to 30 and observe the resulting API request.
  const responsePromise = page.waitForResponse((resp) => {
    try {
      const url = new URL(resp.url());
      return (
        url.pathname === '/assistant/recommendations' &&
        url.searchParams.get('max_results') === '30' &&
        resp.request().method() === 'POST'
      );
    } catch {
      return false;
    }
  });

  await page.getByLabel('Page size').selectOption('30');
  const response = await responsePromise;
  expect(response.ok()).toBeTruthy();

  // Results re-render after the page-size change.
  await expect(offerCards.first()).toBeVisible({ timeout: 30000 });
});

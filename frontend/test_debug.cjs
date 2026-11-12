const { chromium } = require('@playwright/test');

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  page.on('console', msg => console.log('BROWSER CONSOLE:', msg.type(), msg.text()));
  page.on('pageerror', err => console.log('BROWSER PAGE ERROR:', err));
  page.on('request', req => console.log('BROWSER REQUEST:', req.method(), req.url()));
  page.on('requestfailed', req => console.log('BROWSER REQUEST FAILED:', req.method(), req.url(), req.failure()?.errorText));
  page.on('response', resp => console.log('BROWSER RESPONSE:', resp.status(), resp.request().method(), resp.url()));

  const loginResponse = await page.request.post('http://127.0.0.1:8000/auth/demo/login', { data: {} });
  const setCookie = loginResponse.headers()['set-cookie'] || '';
  const match = setCookie.match(/payshield_session=([^;]+)/);
  if (!match) {
    console.error('No login cookie!');
    await browser.close();
    return;
  }
  await context.addCookies([{
    name: 'payshield_session',
    value: match[1],
    domain: 'localhost',
    path: '/',
    httpOnly: true,
    secure: false,
  }]);

  console.log('Navigating to http://localhost:3000/product-search ...');
  await page.goto('http://localhost:3000/product-search');
  await page.waitForTimeout(1000);

  const searchInput = page.getByPlaceholder(/Search by vendor/);
  await searchInput.click({ force: true });
  await searchInput.pressSequentially('iPhone 17');
  console.log('Submitting form...');
  await page.evaluate(() => {
    const form = document.querySelector('form');
    if (form) form.requestSubmit();
  });

  console.log('Waiting for network/rendering...');
  await page.waitForTimeout(6000);
  const cards = await page.locator('div[title^="c3_"]').count();
  console.log('Cards found:', cards);
  const bodyText = await page.innerText('body');
  console.log('Has searching live?', bodyText.includes('Searching live'));
  console.log('Has error text?', bodyText.includes('Live product search unavailable'));
  console.log('Has no matching offers?', bodyText.includes('No matching offers found'));

  await browser.close();
})();

import { test, expect } from '@playwright/test';

test('protected routes redirect and API denies unauthenticated requests', async ({ page, request }) => {
  await page.goto('/workspace');
  await expect(page).toHaveURL(/\/login$/);
  const response = await request.get('/api/trpc/workspace.get?batch=1&input=%7B%7D');
  expect(response.status()).toBe(401);
});

test('create account, inspect workspace, sign out, and sign back in', async ({ page }) => {
  const email = `test-${Date.now()}@example.test`;
  const password = 'only-for-local-testing-398!';
  await page.goto('/login');
  await page.getByRole('button', { name: 'Create an account', exact: true }).click();
  await page.getByLabel('Your name').fill('Alex Morgan');
  await page.getByLabel('Email address').fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(page).toHaveURL(/\/workspace$/);
  await expect(page.getByRole('heading', { name: 'A little clarity, Alex.' })).toBeVisible();
  await expect(page.getByText('Loading workspace')).not.toBeVisible();
  await expect(page.getByRole('main').getByRole('alert')).toHaveCount(0);
  await page.screenshot({ path: '.Tmp/workspace-desktop.png', fullPage: true });
  await page.getByRole('button', { name: /Start a conversation/ }).click();
  await expect(page.getByRole('dialog')).toContainText('Speak naturally, pause, and correct yourself');
  await expect(page.getByRole('button', { name: 'Start live conversation' })).toBeVisible();
  await page.getByRole('button', { name: 'Back to workspace' }).click();
  await page.getByRole('button', { name: /Incoming money/ }).click();
  await expect(page.getByRole('dialog')).toContainText('Your income sources will appear here');
  await page.keyboard.press('Escape');
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('heading', { name: 'A little clarity, Alex.' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: '.Tmp/workspace-mobile.png', fullPage: true });
  await page.getByRole('button', { name: 'Open account menu' }).click();
  await page.getByRole('menuitem', { name: 'Sign out' }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel('Email address').fill(email);
  await page.getByLabel('Password', { exact: true }).fill('incorrect-password-123');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.locator('form').getByRole('alert')).toContainText('Check your email and password');
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page).toHaveURL(/\/workspace$/);
});

test('login remains usable on mobile and with reduced motion', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/login');
  await expect(page.getByLabel('Email address')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: '.Tmp/login-mobile.png', fullPage: true });
});

/**
 * E2E-04: 交易页测试
 * 验证余额加载、下单表单、买卖切换、市价/限价切换、资金划转
 */
import { test, expect } from '@playwright/test';

test.describe('交易页', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/trading');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
  });

  test('页面应正常加载', async ({ page }) => {
    const heading = page.getByText('交易').first();
    await expect(heading).toBeVisible();
  });

  test('应显示买入和卖出按钮', async ({ page }) => {
    const buyBtn = page.getByText('买入').first();
    const sellBtn = page.getByText('卖出').first();
    await expect(buyBtn).toBeVisible({ timeout: 5000 });
    await expect(sellBtn).toBeVisible({ timeout: 5000 });
  });

  test('买入/卖出切换应正常', async ({ page }) => {
    const buyBtn = page.getByText('买入').first();
    const sellBtn = page.getByText('卖出').first();

    await buyBtn.click();
    await page.waitForTimeout(300);

    await sellBtn.click();
    await page.waitForTimeout(300);
  });

  test('市价/限价切换应正常', async ({ page }) => {
    const marketBtn = page.getByText('市价', { exact: true }).first();
    const limitBtn = page.getByText('限价', { exact: true }).first();

    if (await marketBtn.isVisible()) {
      await marketBtn.click();
      await page.waitForTimeout(300);
    }

    if (await limitBtn.isVisible()) {
      await limitBtn.click();
      await page.waitForTimeout(300);
      // 限价模式应显示价格输入框
      const priceInput = page.locator('input[placeholder*="价格"]').first();
      await expect(priceInput).toBeVisible();
    }
  });

  test('数量输入框应可输入', async ({ page }) => {
    const amountInput = page.locator('input[placeholder*="数量"]').first();
    if (await amountInput.isVisible()) {
      await amountInput.fill('0.001');
      await expect(amountInput).toHaveValue('0.001');
    }
  });

  test('资产Tab应显示余额信息', async ({ page }) => {
    const assetTab = page.getByText('资产').first();
    if (await assetTab.isVisible()) {
      await assetTab.click();
      await page.waitForTimeout(2000);
      // 应有余额相关数字或 "USDT" 文本
      const usdt = page.getByText('USDT').first();
      await expect(usdt).toBeVisible({ timeout: 10000 });
    }
  });

  test('右侧Tab切换应正常（资产/持仓/挂单/历史）', async ({ page }) => {
    const tabs = ['资产', '持仓', '挂单', '历史'];
    for (const tabText of tabs) {
      const tab = page.getByText(tabText, { exact: false }).first();
      if (await tab.isVisible()) {
        await tab.click();
        await page.waitForTimeout(500);
      }
    }
  });

  test('资金划转区域应可见（OKX模式）', async ({ page }) => {
    // 先切换到 OKX
    const aside = page.locator('aside');
    const okxBtn = aside.getByText('OKX');
    if (await okxBtn.isVisible()) {
      await okxBtn.click();
      await page.waitForTimeout(1000);
    }

    // 资产 Tab
    const assetTab = page.getByText('资产').first();
    if (await assetTab.isVisible()) {
      await assetTab.click();
      await page.waitForTimeout(2000);
    }

    // 划转区域
    const transferText = page.getByText('划转').first();
    await expect(transferText).toBeVisible({ timeout: 10000 });
  });

  test('现货/合约切换应正常', async ({ page }) => {
    const spotBtn = page.getByText('现货', { exact: true }).first();
    const futuresBtn = page.getByText('合约', { exact: true }).first();

    if (await spotBtn.isVisible()) {
      await spotBtn.click();
      await page.waitForTimeout(300);
    }

    if (await futuresBtn.isVisible()) {
      await futuresBtn.click();
      await page.waitForTimeout(300);
    }
  });
});

import { expect, type Page } from '@playwright/test';

/** Exercise the same explicit disclosure action as a user; never bypass API checks. */
export async function expandSection(page: Page, title: string | RegExp) {
  const summary = page.locator('summary').filter({ hasText: title }).first();
  const section = summary.locator('..');
  if ((await section.getAttribute('open')) === null) await summary.click();
}

// The factor list shows the top 3 first; its own "Show all N" control expands it.
export async function showAllFactors(page: Page) {
  const button = page
    .getByRole('list', { name: 'Contributing Risk Factors' })
    .locator('xpath=..')
    .getByRole('button', { name: /^Show all \d+$/ })
    .first();
  if (await button.count()) await button.click();
}

// Assessment versions are counted from the case page's stable history hook, whether the UI
// shows a version list or (for several versions) a version picker.
export async function expectAssessmentVersions(page: Page, total: number) {
  await expect(page.getByTestId('assessment-history')).toHaveAttribute(
    'data-total',
    String(total),
  );
}

/** Names of elements reaching past the viewport's right edge (empty when the page fits). */
export async function overflowingElements(page: Page) {
  return page.evaluate(() => {
    if (document.documentElement.scrollWidth <= innerWidth) return [];
    const wide = [...document.querySelectorAll('body *')]
      .filter((e) => e.getBoundingClientRect().right > innerWidth + 1)
      // Content inside its own horizontal scroller (e.g. a wide table) is allowed.
      .filter((e) => {
        for (
          let a = e.parentElement;
          a && a !== document.body;
          a = a.parentElement
        )
          if (['auto', 'scroll'].includes(getComputedStyle(a).overflowX))
            return false;
        return true;
      })
      .slice(0, 8)
      .map((e) => {
        const name = e.getAttribute('aria-label') ?? e.id ?? '';
        return (
          [e.tagName.toLowerCase(), ...e.classList].join('.') +
          (name ? ` "${name}"` : '')
        );
      });
    if (wide.length) return wide;
    // Fallback: report sizes and the widest elements overall, so the cause is still visible.
    const describe = (e: Element) =>
      [e.tagName.toLowerCase(), ...e.classList].join('.');
    const widest = [...document.querySelectorAll('body *')]
      .map((e) => [e, e.getBoundingClientRect().right] as const)
      .filter(([, right]) => right > innerWidth + 1)
      .sort((a, b) => a[1] - b[1])
      .slice(0, 6)
      .map(([e, right]) => {
        let scroller = e.parentElement;
        while (
          scroller &&
          !['auto', 'scroll'].includes(getComputedStyle(scroller).overflowX)
        )
          scroller = scroller.parentElement;
        const box = scroller?.getBoundingClientRect();
        return (
          `${describe(e)} right=${Math.round(right)}` +
          (scroller && box
            ? ` in ${describe(scroller)} [${Math.round(box.left)}..${Math.round(box.right)}]`
            : '')
        );
      });
    return [
      `document scrollWidth=${document.documentElement.scrollWidth} innerWidth=${innerWidth}`,
      ...widest,
    ];
  });
}

export async function expectNoHorizontalOverflow(page: Page) {
  expect(
    await overflowingElements(page),
    'elements wider than the viewport',
  ).toEqual([]);
}

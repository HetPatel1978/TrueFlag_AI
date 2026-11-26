// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { InvestigationFactory } from './investigation-api';
import { RegulatoryGuidance } from './regulatory-guidance';

afterEach(() => cleanup());
it('binds guidance retrieval to the selected verified investigation', async () => {
  const referenceSearch = vi.fn();
  const referenceInvestigation = vi
    .fn()
    .mockResolvedValue({ status: 'unavailable', passages: [] });
  const api = (() => ({
    referenceSearch,
    referenceInvestigation,
  })) as unknown as InvestigationFactory;
  render(<RegulatoryGuidance id="case" run="run" api={api} />);
  fireEvent.click(screen.getByText('Regulatory Guidance'));
  fireEvent.change(screen.getByLabelText('Search guidance'), {
    target: { value: 'reporting' },
  });
  fireEvent.click(
    screen.getByRole('button', { name: 'Search approved guidance' }),
  );
  await screen.findByText(/Approved guidance is unavailable/);
  expect(referenceInvestigation).toHaveBeenCalledWith(
    'case',
    'run',
    'reporting',
  );
  expect(referenceSearch).not.toHaveBeenCalled();
});

it('shows unavailable when no approved sources exist without affecting the case', async () => {
  const referenceSearch = vi
    .fn()
    .mockResolvedValue({ status: 'unavailable', passages: [] });
  const api = (() => ({ referenceSearch })) as unknown as InvestigationFactory;
  render(<RegulatoryGuidance id="case" api={api} />);
  fireEvent.click(screen.getByText('Regulatory Guidance'));
  fireEvent.change(screen.getByLabelText('Search guidance'), {
    target: { value: 'reporting' },
  });
  fireEvent.click(
    screen.getByRole('button', { name: 'Search approved guidance' }),
  );
  await screen.findByText(/Approved guidance is unavailable/);
  expect(referenceSearch).toHaveBeenCalledWith('case', 'reporting');
});

it('never displays synthetic references as official guidance', async () => {
  const referenceSearch = vi.fn().mockResolvedValue({
    status: 'available',
    passages: [
      {
        reference_id: 'x',
        title: 'Synthetic fixture',
        section: '1',
        origin: 'synthetic_test',
      },
    ],
  });
  const api = (() => ({ referenceSearch })) as unknown as InvestigationFactory;
  render(<RegulatoryGuidance id="case" api={api} />);
  fireEvent.click(screen.getByText('Regulatory Guidance'));
  fireEvent.change(screen.getByLabelText('Search guidance'), {
    target: { value: 'reporting' },
  });
  fireEvent.click(
    screen.getByRole('button', { name: 'Search approved guidance' }),
  );
  await screen.findByText(/Approved guidance is unavailable/);
  expect(screen.queryByText('Synthetic fixture')).toBeNull();
});

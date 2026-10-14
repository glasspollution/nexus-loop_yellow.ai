import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { screenFixture } from './test/fixture'

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  }))
}

const liveVerification = {
  verdict: 'improved',
  verdict_label: 'Improved in replay',
  gate: 'candidate',
  gate_label: 'Replay supports shipping',
  metric: 'median_turns',
  metric_label: 'Median turns',
  before: 7.25,
  before_display: '7.25 turns',
  after: 5.1,
  after_display: '5.10 turns',
  golden_set_pass: true,
  gate_reason: 'Protected examples did not regress.',
  simulated: true,
  simulation_note: 'Before and after come from the organisers’ replay simulator.',
}

describe('Nexus Loop overview', () => {
  afterEach(() => vi.restoreAllMocks())

  it('loads the backend screen and renders its supplied values', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => jsonResponse(screenFixture))
    render(<App />)

    expect(screen.getByLabelText('Loading the latest analysis')).toBeInTheDocument()
    expect(await screen.findByText('$1,234.50')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Hi there. Your latest agent report is ready.' })).toBeInTheDocument()
    expect(screen.getByText('We reviewed the latest 28 days of customer conversations, tools, handoffs, and outcomes.')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'User profile' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Responses take too many turns/i })).toBeInTheDocument()
    expect(screen.getAllByText('Backend-provided status')).toHaveLength(2)
    expect(document.querySelector('.impact-hero')).toHaveTextContent('Backend-provided status')
    expect(screen.getAllByText('02')).toHaveLength(2)
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/screen', expect.objectContaining({ cache: 'no-store' }))
  })

  it('opens the selected issue bento without reordering or refetching', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => jsonResponse(screenFixture))
    render(<App />)

    const secondIssue = await screen.findByRole('button', { name: /A lookup is not returning answers/i })
    fireEvent.click(secondIssue)
    expect(screen.getAllByText('$245.00')).not.toHaveLength(0)
    const dialog = screen.getByRole('dialog', { name: 'Example configuration issue' })
    await waitFor(() => expect(within(dialog).getByRole('heading', { name: 'Example configuration issue' })).toHaveFocus())
    const bento = within(dialog).getByRole('region', { name: 'Issue detection and diagnosis summary' })
    expect(within(bento).getByRole('button', { name: /Days running: 10 days/i })).toBeInTheDocument()
    expect(within(bento).getByRole('button', { name: /Mechanism metric: 7.0/i })).toBeInTheDocument()
    expect(globalThis.fetch).toHaveBeenCalledTimes(1)
  })

  it('previews each issue impact on hover and keyboard focus without opening the dialog', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => jsonResponse(screenFixture))
    render(<App />)

    const firstIssue = await screen.findByRole('button', { name: /Responses take too many turns/i })
    const secondIssue = screen.getByRole('button', { name: /A lookup is not returning answers/i })
    const impactCard = document.querySelector('.impact-card') as HTMLElement

    expect(within(impactCard).getByText('$1,234.50')).toBeInTheDocument()

    fireEvent.mouseEnter(secondIssue)
    expect(within(impactCard).getByText('$245.00')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    fireEvent.focus(firstIssue)
    expect(within(impactCard).getByText('$1,234.50')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(globalThis.fetch).toHaveBeenCalledTimes(1)
  })

  it('opens the issue currently clicked after a hover preview without another fetch', async () => {
    const distinctIssues = {
      ...screenFixture,
      findings: screenFixture.findings.map((finding, index) => index === 1
        ? {
            ...finding,
            diagnosis: finding.diagnosis
              ? { ...finding.diagnosis, label: 'Second backend diagnosis' }
              : finding.diagnosis,
          }
        : finding),
    }
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => jsonResponse(distinctIssues))
    render(<App />)

    const secondIssue = await screen.findByRole('button', { name: /A lookup is not returning answers/i })
    fireEvent.mouseEnter(secondIssue)
    fireEvent.click(secondIssue)

    expect(screen.getByRole('dialog', { name: 'Second backend diagnosis' })).toBeInTheDocument()
    expect(globalThis.fetch).toHaveBeenCalledTimes(1)
  })

  it('keeps manager details quiet until their info controls are opened', async () => {
    const fixtureWithContext = {
      ...screenFixture,
      disclosures: { analysis_limits: ['Backend-provided analysis limit.'] },
    }
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => jsonResponse(fixtureWithContext))
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Responses take too many turns/i }))
    const dialog = screen.getByRole('dialog', { name: 'Example configuration issue' })

    expect(within(dialog).queryByRole('heading', { name: 'Baseline' })).not.toBeInTheDocument()
    expect(within(dialog).queryByRole('heading', { name: 'Who acts' })).not.toBeInTheDocument()
    expect(dialog.querySelector('.issue-bento__bars')).not.toBeInTheDocument()

    const issueInfo = within(dialog).getByRole('button', { name: 'Issue context' })
    expect(issueInfo).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(issueInfo)
    expect(issueInfo).toHaveAttribute('aria-expanded', 'true')
    expect(within(dialog).getByText('Responses take too many turns')).toBeVisible()

    expect(within(dialog).getByText('Approve a guarded configuration adjustment.')).toBeVisible()
    expect(within(dialog).getByText('The change may not improve the affected conversations.')).toBeVisible()
    expect(within(dialog).getByText('The protected examples regress.')).toBeVisible()
    expect(within(dialog).getByText('The safer path may respond more slowly.')).toBeVisible()
    expect(within(dialog).queryByText('Restore the previously successful behavior for this cohort.')).not.toBeInTheDocument()

    const proposalDetails = within(dialog).getByRole('button', { name: 'Proposal technical details' })
    expect(proposalDetails).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(proposalDetails)
    expect(proposalDetails).toHaveAttribute('aria-expanded', 'true')
    expect(within(dialog).getByText('Restore the previously successful behavior for this cohort.')).toBeVisible()

    const evidenceSummary = within(dialog).getByText('Evidence', { selector: 'summary' })
    const evidence = evidenceSummary.closest('details')
    expect(evidence).not.toHaveAttribute('open')
    expect(evidence?.closest('footer')).toHaveClass('issue-dialog__footer')
    expect(within(dialog).getByRole('button', { name: 'About this analysis' })).toHaveAttribute('aria-expanded', 'false')
  })

  it('closes an info panel from inside the panel and restores trigger focus', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => jsonResponse(screenFixture))
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Responses take too many turns/i }))
    const dialog = screen.getByRole('dialog', { name: 'Example configuration issue' })
    const trigger = within(dialog).getByRole('button', { name: 'Issue context' })

    fireEvent.click(trigger)
    const close = within(dialog).getByRole('button', { name: 'Close Issue context' })
    fireEvent.click(close)

    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    await waitFor(() => expect(trigger).toHaveFocus())
    expect(within(dialog).queryByRole('region', { name: 'Issue context' })).not.toBeInTheDocument()
  })

  it('shows backend-dismissed lookalikes in a compact disclosure with evidence last', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => jsonResponse(screenFixture))
    render(<App />)

    const trigger = await screen.findByRole('button', { name: '1 lookalike ruled out by the engine' })
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('button', { name: /Review issue/i })).not.toBeInTheDocument()

    fireEvent.click(trigger)
    expect(trigger).toHaveAttribute('aria-expanded', 'true')
    const panel = screen.getByRole('region', { name: 'Lookalikes ruled out by the engine' })
    expect(within(panel).getByText('Backend traffic surge')).toBeInTheDocument()
    expect(within(panel).getByText(/Demo Tenant · all traffic · Days 8–12/)).toBeInTheDocument()

    fireEvent.click(within(panel).getByText('Backend traffic surge'))
    expect(within(panel).getByText('Backend analysis found that the signal ended when traffic returned to normal.')).toBeVisible()
    const evidence = within(panel).getByText('Evidence')
    const body = evidence.closest('.dismissed-lookalike__body')
    expect(body?.lastElementChild).toContainElement(evidence)

    fireEvent.click(evidence)
    expect(within(panel).getByText('Backend evidence: latency moved across every cohort at once.')).toBeVisible()
    expect(within(panel).getByText('Backend evidence: the deviation ended with the traffic surge.')).toBeVisible()
  })

  it('closes the dismissed-lookalike panel with Escape and restores trigger focus', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => jsonResponse(screenFixture))
    render(<App />)

    const trigger = await screen.findByRole('button', { name: '1 lookalike ruled out by the engine' })
    fireEvent.click(trigger)
    fireEvent.keyDown(document, { key: 'Escape' })

    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    expect(trigger).toHaveFocus()
    expect(screen.queryByRole('region', { name: 'Lookalikes ruled out by the engine' })).not.toBeInTheDocument()
  })

  it('reopens dismissed lookalikes with its rows, evidence, and scroll reset', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => jsonResponse(screenFixture))
    render(<App />)

    const trigger = await screen.findByRole('button', { name: '1 lookalike ruled out by the engine' })
    fireEvent.click(trigger)
    const panel = screen.getByRole('region', { name: 'Lookalikes ruled out by the engine' })

    fireEvent.click(within(panel).getByText('Backend traffic surge'))
    const itemDetails = within(panel).getByText('Backend traffic surge').closest('details')
    const evidenceSummary = within(panel).getByText('Evidence')
    fireEvent.click(evidenceSummary)
    const evidenceDetails = evidenceSummary.closest('details')
    expect(itemDetails).toHaveAttribute('open')
    expect(evidenceDetails).toHaveAttribute('open')

    panel.scrollTop = 120
    fireEvent.click(within(panel).getByRole('button', { name: 'Close dismissed lookalikes' }))
    fireEvent.click(trigger)

    const reopenedPanel = screen.getByRole('region', { name: 'Lookalikes ruled out by the engine' })
    expect(reopenedPanel.scrollTop).toBe(0)
    expect(within(reopenedPanel).getByText('Backend traffic surge').closest('details')).not.toHaveAttribute('open')
    expect(within(reopenedPanel).getByText('Evidence').closest('details')).not.toHaveAttribute('open')
    expect(within(reopenedPanel).getByText('Backend evidence: latency moved across every cohort at once.')).not.toBeVisible()
  })

  it('makes a displayed number definition available from the keyboard', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => jsonResponse(screenFixture))
    render(<App />)

    const value = await screen.findByRole('button', { name: /Extra spend against the baseline: \$1,234.50/i })
    fireEvent.click(value)
    expect(screen.getByRole('tooltip')).toHaveTextContent('Definition for extra spend against the baseline.')
  })

  it('submits a hash-bound decision and replaces state from the backend response', async () => {
    const accepted = {
      ...screenFixture,
      findings: screenFixture.findings.map((finding, index) => index === 0
        ? {
            ...finding,
            approval: { state: 'accepted', label: 'Approved', decided_by: 'Demo manager', reason: 'Evidence reviewed.' },
            verification: liveVerification,
          }
        : finding),
    }
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() => jsonResponse(screenFixture))
      .mockImplementationOnce(() => jsonResponse({ result: { saved: true }, screen: accepted }))
    render(<App />)

    await screen.findByText('$1,234.50')
    fireEvent.click(screen.getByRole('button', { name: /Responses take too many turns/i }))
    expect(screen.queryByRole('region', { name: 'Live apply and replay outcome' })).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Your name'), { target: { value: 'Demo manager' } })
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Evidence reviewed.' } })
    fireEvent.click(screen.getByRole('radio', { name: 'Approve' }))
    fireEvent.click(screen.getByRole('button', { name: 'Approve and run live replay' }))

    const receipt = await screen.findByRole('region', { name: 'Recorded decision' })
    expect(within(receipt).getByText('Approved')).toBeInTheDocument()
    expect(within(receipt).getByText(/Applied for this session’s sandbox replay only/)).toBeInTheDocument()
    const outcome = screen.getByRole('region', { name: 'Live apply and replay outcome' })
    expect(within(outcome).getByText('5.10 turns')).toBeInTheDocument()
    const request = fetchMock.mock.calls[1]
    expect(request[0]).toBe('/api/decisions')
    expect(JSON.parse(String((request[1] as RequestInit).body))).toMatchObject({
      prescription_id: 'p-f-1',
      verdict: 'accepted',
      proposal_sha: 'sha-f-1',
      generated_report_sha256: 'generated-sha',
    })
  })

  it('never exposes an apply or replay outcome while the decision is pending', async () => {
    const pendingWithStaleVerification = {
      ...screenFixture,
      findings: screenFixture.findings.map((finding, index) => index === 0
        ? {
            ...finding,
            verification: liveVerification,
          }
        : finding),
    }
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => jsonResponse(pendingWithStaleVerification))
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Responses take too many turns/i }))
    const dialog = screen.getByRole('dialog', { name: 'Example configuration issue' })
    const decisionGroup = within(dialog).getByRole('group', { name: 'Record your decision' })

    expect(within(dialog).queryByRole('region', { name: 'Live apply and replay outcome' })).not.toBeInTheDocument()
    expect(within(dialog).queryByText('Improved in replay')).not.toBeInTheDocument()
    expect(within(dialog).getByText(/Approve applies the proposal in this session and runs a live sandbox replay/)).toBeVisible()

    for (const option of within(decisionGroup).getAllByRole('radio')) {
      expect(option).not.toBeChecked()
      expect(option).toBeRequired()
    }
    expect(within(dialog).getByText('Choose one option. Your name and reason are required.')).toBeVisible()
    expect(within(dialog).getByRole('button', { name: 'Record decision' })).toBeDisabled()
  })

  it('records a rejection with the backend hashes', async () => {
    const rejected = {
      ...screenFixture,
      findings: screenFixture.findings.map((finding, index) => index === 0
        ? {
            ...finding,
            approval: { state: 'rejected', label: 'Rejected', decided_by: 'Demo manager', reason: 'Risk is too high.' },
            verification: liveVerification,
          }
        : finding),
    }
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() => jsonResponse(screenFixture))
      .mockImplementationOnce(() => jsonResponse({ result: { saved: true }, screen: rejected }))
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Responses take too many turns/i }))
    fireEvent.click(screen.getByRole('radio', { name: 'Reject' }))
    fireEvent.change(screen.getByLabelText('Your name'), { target: { value: 'Demo manager' } })
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Risk is too high.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Record rejection' }))

    const receipt = await screen.findByRole('region', { name: 'Recorded decision' })
    expect(within(receipt).getByText('Recorded for this session. No change was applied and no replay was run.')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Live apply and replay outcome' })).not.toBeInTheDocument()
    expect(JSON.parse(String((fetchMock.mock.calls[1][1] as RequestInit).body))).toMatchObject({
      prescription_id: 'p-f-1',
      verdict: 'rejected',
      proposal_sha: 'sha-f-1',
      generated_report_sha256: 'generated-sha',
    })
  })

  it('records a deferral without exposing an applied or replayed result', async () => {
    const deferred = {
      ...screenFixture,
      findings: screenFixture.findings.map((finding, index) => index === 0
        ? {
            ...finding,
            approval: { state: 'deferred', label: 'Deferred', decided_by: 'Demo manager', reason: 'Wait for the next review.' },
            verification: liveVerification,
          }
        : finding),
    }
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() => jsonResponse(screenFixture))
      .mockImplementationOnce(() => jsonResponse({ result: { saved: true }, screen: deferred }))
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Responses take too many turns/i }))
    fireEvent.click(screen.getByRole('radio', { name: 'Defer' }))
    fireEvent.change(screen.getByLabelText('Your name'), { target: { value: 'Demo manager' } })
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Wait for the next review.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Record deferral' }))

    const receipt = await screen.findByRole('region', { name: 'Recorded decision' })
    expect(within(receipt).getByText('Deferred')).toBeInTheDocument()
    expect(within(receipt).getByText('Recorded for this session. No change was applied and no replay was run.')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Live apply and replay outcome' })).not.toBeInTheDocument()
    expect(JSON.parse(String((fetchMock.mock.calls[1][1] as RequestInit).body))).toMatchObject({ verdict: 'deferred' })
  })

  it('announces that an approval is applying and replaying while the backend response is pending', async () => {
    const accepted = {
      ...screenFixture,
      findings: screenFixture.findings.map((finding, index) => index === 0
        ? {
            ...finding,
            approval: { state: 'accepted', label: 'Approved', decided_by: 'Demo manager', reason: 'Run it live.' },
            verification: liveVerification,
          }
        : finding),
    }
    let finishDecision: ((response: Response) => void) | undefined
    const pendingDecision = new Promise<Response>((resolve) => {
      finishDecision = resolve
    })
    vi.spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() => jsonResponse(screenFixture))
      .mockImplementationOnce(() => pendingDecision)
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Responses take too many turns/i }))
    fireEvent.click(screen.getByRole('radio', { name: 'Approve' }))
    fireEvent.change(screen.getByLabelText('Your name'), { target: { value: 'Demo manager' } })
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Run it live.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Approve and run live replay' }))

    const dialog = screen.getByRole('dialog', { name: 'Example configuration issue' })
    const progress = within(dialog).getByRole('status')
    expect(progress).toHaveTextContent('Approval is running live in the background')
    expect(progress).toHaveTextContent('applying the approved proposal for this session and running replay')
    expect(within(dialog).getByRole('button', { name: 'Applying and replaying…' })).toBeDisabled()
    expect(within(dialog).getByRole('button', { name: 'Close issue review' })).toBeDisabled()
    expect(within(dialog).queryByRole('region', { name: 'Live apply and replay outcome' })).not.toBeInTheDocument()

    finishDecision?.(await jsonResponse({ result: { saved: true }, screen: accepted }))
    expect(await within(dialog).findByRole('region', { name: 'Live apply and replay outcome' })).toBeInTheDocument()
  })

  it('keeps a stale decision open and requires review of the refreshed backend proposal', async () => {
    const refreshed = {
      ...screenFixture,
      findings: screenFixture.findings.map((finding, index) => index === 0 && finding.proposal
        ? {
            ...finding,
            proposal: {
              ...finding.proposal,
              proposal_sha: 'sha-f-1-updated',
              decision: {
                ...finding.proposal.decision,
                asking_approval_for: 'Review the backend-updated recommendation.',
              },
            },
          }
        : finding),
    }
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() => jsonResponse(screenFixture))
      .mockImplementationOnce(() => jsonResponse({ error: 'stale proposal' }, 409))
      .mockImplementationOnce(() => jsonResponse(refreshed))
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Responses take too many turns/i }))
    fireEvent.click(screen.getByRole('radio', { name: 'Reject' }))
    fireEvent.change(screen.getByLabelText('Your name'), { target: { value: 'Demo manager' } })
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Needs another review.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Record rejection' }))

    const dialog = await screen.findByRole('dialog', { name: 'Example configuration issue' })
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('This proposal changed')
    expect(within(dialog).getByText('Review the backend-updated recommendation.')).toBeVisible()
    for (const option of within(dialog).getAllByRole('radio')) expect(option).not.toBeChecked()
    expect(within(dialog).getByLabelText('Your name')).toHaveValue('')
    expect(within(dialog).getByLabelText('Reason')).toHaveValue('')
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(fetchMock.mock.calls[2][0]).toBe('/api/screen')
  })

  it('shows the backend failure honestly when an approved live replay is unavailable', async () => {
    const acceptedWithoutReplay = {
      ...screenFixture,
      findings: screenFixture.findings.map((finding, index) => index === 0
        ? {
            ...finding,
            approval: { state: 'accepted', label: 'Approved', decided_by: 'Demo manager', reason: 'Proceed with the live run.' },
            verification: { gate: 'unverified', gate_label: 'Replay unavailable', reason: 'The live replay engine did not respond.' },
          }
        : finding),
    }
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => jsonResponse(acceptedWithoutReplay))
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Responses take too many turns/i }))
    const dialog = screen.getByRole('dialog', { name: 'Example configuration issue' })
    const replay = within(dialog).getByRole('region', { name: 'Live apply and replay outcome' })

    expect(within(replay).getByText('Replay unavailable')).toBeInTheDocument()
    expect(within(replay).getByText('The live replay engine did not respond.')).toBeInTheDocument()
    expect(within(replay).getByText(/approval was recorded, but replay did not return a result/i)).toBeInTheDocument()
    expect(within(dialog).queryByRole('group', { name: 'Record your decision' })).not.toBeInTheDocument()
  })

  it('replaces a recorded form with a receipt and makes edits start blank', async () => {
    const decided = {
      ...screenFixture,
      findings: screenFixture.findings.map((finding, index) => index === 0
        ? {
            ...finding,
            approval: {
              state: 'accepted',
              label: 'Approved',
              decided_by: 'Previous manager',
              reason: 'Previously recorded reason.',
              at: '2026-01-14T11:00:00Z',
            },
            verification: liveVerification,
          }
        : finding),
    }
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => jsonResponse(decided))
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Responses take too many turns/i }))
    const dialog = screen.getByRole('dialog', { name: 'Example configuration issue' })
    const receipt = within(dialog).getByRole('region', { name: 'Recorded decision' })
    expect(within(receipt).getByText('Approved')).toBeInTheDocument()
    expect(within(dialog).queryByRole('group', { name: 'Record your decision' })).not.toBeInTheDocument()

    fireEvent.click(within(receipt).getByRole('button', { name: 'Change decision' }))
    const editGroup = within(dialog).getByRole('group', { name: 'Change recorded decision' })
    await waitFor(() => expect(within(editGroup).getByRole('radio', { name: 'Approve' })).toHaveFocus())
    for (const option of within(editGroup).getAllByRole('radio')) {
      expect(option).not.toBeChecked()
    }
    expect(within(dialog).getByLabelText('Your name')).toHaveValue('')
    expect(within(dialog).getByLabelText('Reason')).toHaveValue('')

    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    const restoredReceipt = within(dialog).getByRole('region', { name: 'Recorded decision' })
    await waitFor(() => expect(restoredReceipt).toHaveFocus())
    expect(within(dialog).queryByRole('group', { name: 'Change recorded decision' })).not.toBeInTheDocument()
  })

  it('clears an unfinished decision when the same issue is reopened', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => jsonResponse(screenFixture))
    render(<App />)

    const issue = await screen.findByRole('button', { name: /Responses take too many turns/i })
    fireEvent.click(issue)
    fireEvent.click(screen.getByRole('radio', { name: 'Reject' }))
    fireEvent.change(screen.getByLabelText('Your name'), { target: { value: 'Unsubmitted manager' } })
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Unsubmitted reason.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Close issue review' }))

    fireEvent.click(issue)
    const dialog = screen.getByRole('dialog', { name: 'Example configuration issue' })
    const decisionGroup = within(dialog).getByRole('group', { name: 'Record your decision' })
    for (const option of within(decisionGroup).getAllByRole('radio')) {
      expect(option).not.toBeChecked()
    }
    expect(within(dialog).getByLabelText('Your name')).toHaveValue('')
    expect(within(dialog).getByLabelText('Reason')).toHaveValue('')
    expect(within(dialog).getByRole('button', { name: 'Record decision' })).toBeDisabled()
  })

  it('returns to the receipt after updating a recorded decision to the same verdict', async () => {
    const initiallyAccepted = {
      ...screenFixture,
      findings: screenFixture.findings.map((finding, index) => index === 0
        ? {
            ...finding,
            approval: { state: 'accepted', label: 'Approved', decided_by: 'First manager', reason: 'Original reason.' },
            verification: liveVerification,
          }
        : finding),
    }
    const updatedAccepted = {
      ...initiallyAccepted,
      findings: initiallyAccepted.findings.map((finding, index) => index === 0
        ? { ...finding, approval: { state: 'accepted', label: 'Approved', decided_by: 'Second manager', reason: 'Updated reason.' } }
        : finding),
    }
    vi.spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() => jsonResponse(initiallyAccepted))
      .mockImplementationOnce(() => jsonResponse({ result: { saved: true }, screen: updatedAccepted }))
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /Responses take too many turns/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Change decision' }))
    fireEvent.click(screen.getByRole('radio', { name: 'Approve' }))
    fireEvent.change(screen.getByLabelText('Your name'), { target: { value: 'Second manager' } })
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Updated reason.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Approve and run live replay' }))

    const receipt = await screen.findByRole('region', { name: 'Recorded decision' })
    await waitFor(() => expect(receipt).toHaveFocus())
    expect(within(receipt).getByText('Updated reason.')).toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Change recorded decision' })).not.toBeInTheDocument()
  })

  it('shows an actionable error and retries', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockRejectedValueOnce(new TypeError('offline'))
      .mockImplementationOnce(() => jsonResponse(screenFixture))
    render(<App />)

    expect(await screen.findByText('We couldn’t load the review')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(screen.getByText('$1,234.50')).toBeInTheDocument())
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('explains when the development frontend is running without its backend', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => Promise.resolve(new Response('', {
      status: 500,
      headers: { 'Content-Type': 'text/plain' },
    })))
    render(<App />)

    expect(await screen.findByText(/frontend is running, but the Nexus Loop backend is unavailable/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  it('shows a clear empty state when the backend reports no findings', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => jsonResponse({
      ...screenFixture,
      summary: { ...screenFixture.summary, regressions: 0, decisions_pending: 0 },
      findings: [],
    }))
    render(<App />)

    expect(await screen.findByRole('heading', { name: /Your latest analysis is clear/i })).toBeInTheDocument()
    const trigger = screen.getByRole('button', { name: '1 lookalike ruled out by the engine' })
    fireEvent.click(trigger)
    expect(screen.getByRole('region', { name: 'Lookalikes ruled out by the engine' })).toHaveTextContent('Backend traffic surge')
  })

  it('omits the dismissed-lookalike control when the backend reports none', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => jsonResponse({
      ...screenFixture,
      summary: { ...screenFixture.summary, dismissed: 0 },
      dismissed: [],
    }))
    render(<App />)

    await screen.findByText('$1,234.50')
    expect(screen.queryByRole('button', { name: /lookalike.*ruled out by the engine/i })).not.toBeInTheDocument()
  })

  it('rejects an incompatible screen contract', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => jsonResponse({ ...screenFixture, screen_version: 'future/2' }))
    render(<App />)

    expect(await screen.findByText(/incompatible screen format/i)).toBeInTheDocument()
  })
})

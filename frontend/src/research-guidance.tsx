import { useEffect, useState } from 'react';
import { ApiError, message } from './api';
import type {
  InvestigationFactory,
  ResearchContext,
} from './investigation-api';

type Props = {
  id: string;
  api: InvestigationFactory;
  invalidate: (error: unknown) => void;
};

export function ResearchGuidance(props: Props) {
  return <ResearchGuidanceContent key={props.id} {...props} />;
}

function ResearchGuidanceContent({ id, api, invalidate }: Props) {
  const [context, setContext] = useState<ResearchContext | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    const read = api(controller.signal).researchContext;
    if (read)
      void read(id)
        .then((value) => {
          if (
            !controller.signal.aborted &&
            value.status === 'research_unapproved' &&
            value.publication_approved === false
          )
            setContext(value);
        })
        .catch((failure) => {
          if (controller.signal.aborted) return;
          setContext(null);
          if (
            failure instanceof ApiError &&
            [401, 403].includes(failure.status)
          )
            invalidate(failure);
          else if (!(failure instanceof ApiError && failure.status === 404))
            setError(message(failure));
        });
    return () => controller.abort();
  }, [id, api, invalidate]);
  if (!context && !error) return null;
  return (
    <section className="panel" aria-label="Regulatory Research / Unapproved">
      <h3>
        Regulatory Research <span className="muted">/ Unapproved</span>
      </h3>
      {error && <p role="alert">{error}</p>}
      {context && (
        <>
          <p role="note">
            <strong>
              Unapproved research · Not production regulatory guidance
            </strong>
          </p>
          <p role="note">{context.notice}</p>
          {context.dispatch_binding_status === 'expired' && (
            <p role="status">
              The evidence window of the latest prepared request has closed.
              Generate investigation prepares a fresh request for approval.
            </p>
          )}
          <p className="muted">
            Historical U.S. bank research context. Applicability and legal
            interpretation require independent review. Claude execution requires
            separate exact-request approval.
          </p>
          {context.passages.map((passage) => (
            <details key={passage.reference_id}>
              <summary>
                31 CFR § {passage.section} · {passage.historical_as_of}
              </summary>
              <p>{passage.publisher}</p>
              <p style={{ whiteSpace: 'pre-wrap' }} data-ui-guard-skip>
                {passage.text}
              </p>
              {passage.source_url.startsWith(
                'https://www.ecfr.gov/api/versioner/',
              ) && (
                <a href={passage.source_url} target="_blank" rel="noreferrer">
                  Open historical eCFR source
                </a>
              )}
              <p className="muted" title={passage.reference_id}>
                Reference {passage.reference_id.slice(0, 8)}
              </p>
              <details data-ui-guard-skip>
                <summary>Source identity</summary>
                <p>Original SHA-256: {passage.raw_sha256}</p>
                <p>Passage SHA-256: {passage.text_sha256}</p>
              </details>
            </details>
          ))}
        </>
      )}
    </section>
  );
}

"""Light service list view: read path, fallback and the "full source_ref before save" rule.

The list is read from mindex_worship_services_list (source_ref without the stored document and
history). When the view is not deployed the app reads the table as before. A service read from the
view is "partial": its full source_ref is fetched when it is opened and saving is refused until then,
because a save merges the previous history into the outgoing source_ref.
"""

from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            browser = launch_chromium(p)
            page = browser.new_page()
            page.route('**/*supabase*/**', lambda route: route.abort())
            page.goto(url, wait_until='domcontentloaded')
            page.wait_for_function("typeof fetchWorshipServiceListRows === 'function' && typeof ensureFullServiceSourceRef === 'function'")
            result = page.evaluate("""async () => {
              const check = (ok, message) => { if (!ok) throw new Error(message); };
              const DOC = MINDEX_SERVICE_DOCUMENT_SOURCE_REF_KEY, HIST = MINDEX_SERVICE_DOCUMENT_HISTORY_SOURCE_REF_KEY;
              const fullRef = { friday_variant: 'x', [DOC]: { kind: MINDEX_SERVICE_DOCUMENT_KIND, version: MINDEX_SERVICE_DOCUMENT_VERSION, serviceId: 's1', sourceText: 'stored text' },
                [HIST]: [{ kind: MINDEX_SERVICE_DOCUMENT_KIND, version: MINDEX_SERVICE_DOCUMENT_VERSION, serviceId: 's1', sourceText: 'older text' }] };
              const lightRow = (id, flags) => ({ id, service_type_id: 'sunday-main', service_date: '2026-09-13', title: '', status: 'draft', source_ref: { friday_variant: 'x' }, ...flags });
              const calls = [];
              // Chainable/awaitable query builder standing in for supabase-js.
              const client = (handlers) => ({ from(table) {
                const q = { table, filters: [], select(cols) { q.cols = cols; return q; }, order() { return q; }, eq(k, v) { q.filters.push([k, v]); return q; },
                  range() { calls.push(['range', table]); return Promise.resolve(handlers.list(table)); },
                  maybeSingle() { calls.push(['maybeSingle', table, q.cols]); return Promise.resolve(handlers.single(table, q)); } };
                return q; } });
              const prev = { client: state.client, services: state.services, view: state.serviceListViewSupported, alias: state.serviceAliasSupported };
              state.serviceAliasSupported = true;
              localStorage.removeItem(WORSHIP_LIST_VIEW_MISSING_KEY);
              try {
                // 1) view is deployed: light rows, flags mark the ones that lost a payload
                state.serviceListViewSupported = undefined;
                state.client = client({
                  list: (table) => table === WORSHIP_SERVICE_LIST_VIEW
                    ? { data: [lightRow('s1', { has_service_document: true, has_service_document_history: true }), lightRow('s2', { has_service_document: false, has_service_document_history: false })], error: null }
                    : { data: [], error: new Error('table must not be read') },
                  single: () => ({ data: { source_ref: fullRef }, error: null }),
                });
                const rows = await fetchWorshipServiceListRows();
                check(rows.length === 2 && state.serviceListViewSupported === true, 'view rows expected');
                check(calls.every((c) => c[1] === WORSHIP_SERVICE_LIST_VIEW), 'only the view should be read');
                const [s1, s2] = rows.map(normalizeWorshipService);
                check(s1._worshipSourceRefPartial === true && s2._worshipSourceRefPartial === false, 'partial flag follows has_service_document*');

                // 2) partial service: hard invariant and save guard
                state.services = [s1, s2];
                let threw = false;
                try { withServiceDocumentSnapshot(s1, []); } catch { threw = true; }
                check(threw, 'a list-only source_ref must not be turned into an outgoing source_ref');
                state.client = client({ list: () => ({ data: [], error: null }), single: () => ({ data: null, error: new Error('offline') }) });
                let refused = false;
                try { await requireFullServiceSourceRef('s1'); } catch { refused = true; }
                check(refused && s1._worshipSourceRefPartial === true, 'save must be refused while the full source_ref is unavailable');
                check((await requireFullServiceSourceRef('s2')) === undefined, 'a service with nothing stripped saves immediately');

                // 3) opening loads the rest and keeps local edits of the light keys
                s1._worshipSourceRef = { ...s1._worshipSourceRef, dedication_service: true };
                calls.length = 0;
                state.client = client({ list: () => ({ data: [], error: null }), single: () => ({ data: { source_ref: fullRef }, error: null }) });
                await Promise.all([ensureFullServiceSourceRef('s1'), ensureFullServiceSourceRef('s1')]);
                check(calls.filter((c) => c[0] === 'maybeSingle').length === 1, 'concurrent opens share one request');
                check(calls[0][2] === 'source_ref' && calls[0][1] === 'mindex_worship_services', 'full row is read from the table');
                check(s1._worshipSourceRefPartial === false, 'flag cleared after loading');
                const ref = serviceSourceRef(s1);
                check(ref[DOC]?.sourceText === 'stored text' && ref[HIST]?.length === 1, 'document and history restored');
                check(ref.dedication_service === true && ref.friday_variant === 'x', 'local light keys kept');
                check(typeof withServiceDocumentSnapshot(s1, []) === 'object', 'saving is allowed after loading');

                // 4) view not deployed: fall back to the table once, remember it
                state.serviceListViewSupported = undefined; calls.length = 0;
                state.client = client({
                  list: (table) => table === WORSHIP_SERVICE_LIST_VIEW
                    ? { data: null, error: { code: 'PGRST205', message: "Could not find the table 'public.mindex_worship_services_list' in the schema cache" } }
                    : { data: [lightRow('s3', {})], error: null },
                  single: () => ({ data: null, error: null }),
                });
                const fallback = await fetchWorshipServiceListRows();
                check(fallback.length === 1 && state.serviceListViewSupported === false, 'fallback to the table');
                check(normalizeWorshipService(fallback[0])._worshipSourceRefPartial === false, 'table rows are complete');
                calls.length = 0; await fetchWorshipServiceListRows();
                check(calls.every((c) => c[1] === 'mindex_worship_services'), 'the missing view is not probed again');
                check(worshipListViewKnownMissing(), 'the missing view is remembered for a while');
                state.serviceListViewSupported = undefined; calls.length = 0; await fetchWorshipServiceListRows();
                check(calls.every((c) => c[1] === 'mindex_worship_services'), 'a fresh page load does not probe a view known to be missing');
                localStorage.removeItem(WORSHIP_LIST_VIEW_MISSING_KEY);

                // 5) an outage on the view is not mistaken for "not deployed"
                state.serviceListViewSupported = undefined;
                state.client = client({ list: () => ({ data: null, error: new Error('Failed to fetch') }), single: () => ({ data: null, error: null }) });
                calls.length = 0;
                let outcome = 'rows';
                try { await fetchWorshipServiceListRows(); } catch { outcome = 'threw'; }
                // Either the cached list answers or the error propagates; the table is not read instead
                // and the view is not marked unsupported.
                check(state.serviceListViewSupported === undefined, 'a network error must not disable the view');
                check(!calls.some((c) => c[1] === 'mindex_worship_services'), 'the table must not be read on an outage (' + outcome + ')');
                return 'ok';
              } finally {
                state.client = prev.client; state.services = prev.services;
                state.serviceListViewSupported = prev.view; state.serviceAliasSupported = prev.alias;
                localStorage.removeItem(WORSHIP_LIST_VIEW_MISSING_KEY);
              }
            }""")
            assert result == 'ok', result
            print('PASS service list view read, fallback, and full source_ref before save', flush=True)
            browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()

"""Cache invalidation contracts for the render-time caches.

- serviceSourceRef() caches the normalized document per raw object, but a key
  reassigned in place (or a replaced object) must be visible immediately.
- getServiceItems() reuses one projection inside a render scope only while
  state.serviceItems[serviceId] is still the array that projection produced.
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
            page.wait_for_function("typeof serviceSourceRef === 'function' && typeof withServiceItemsScope === 'function'")
            result = page.evaluate("""() => {
              const check = (ok, message) => { if (!ok) throw new Error(message); };
              const DOC = MINDEX_SERVICE_DOCUMENT_SOURCE_REF_KEY;
              const doc = (text) => ({ kind: MINDEX_SERVICE_DOCUMENT_KIND, version: MINDEX_SERVICE_DOCUMENT_VERSION, serviceId: 's', sourceText: text });

              // --- serviceSourceRef cache
              const service = { id: 's', type_id: 'sunday-main', date: '2026-09-13', _worshipSourceRef: { friday_variant: 'x', [DOC]: doc('one') } };
              const first = serviceSourceRef(service);
              check(serviceSourceRef(service) === first, 'unchanged source ref should reuse the normalized result');
              check(serviceRawSourceRef(service).friday_variant === 'x', 'raw reader must read the field directly');
              service._worshipSourceRef[DOC] = doc('two');
              const afterInPlace = serviceSourceRef(service);
              check(afterInPlace !== first && afterInPlace[DOC].sourceText === 'two', 'in-place key reassignment must invalidate');
              service._worshipSourceRef = { ...service._worshipSourceRef, friday_variant: 'y' };
              check(serviceSourceRef(service).friday_variant === 'y', 'replaced source ref must be re-read');
              check(serviceFridayVariantKey(service) === 'y', 'scalar lookups must follow the raw ref');
              check(JSON.stringify(serviceSourceRef({})) === '{}' && JSON.stringify(serviceSourceRef(null)) === '{}', 'empty inputs');

              // --- getServiceItems render scope
              const svc = { id: '__scope__', type_id: 'sunday-main', date: '2026-09-13', title: '주일예배 [3부]' };
              const previousServices = state.services;
              const previousItems = state.serviceItems[svc.id];
              const previousProject = projectWorshipServiceItemsFromTemplate;
              let projections = 0;
              projectWorshipServiceItemsFromTemplate = (...args) => { projections += 1; return previousProject(...args); };
              try {
                state.services = [svc, ...previousServices];
                state.serviceItems[svc.id] = [];
                projections = 0;
                getServiceItems(svc.id); getServiceItems(svc.id);
                check(projections === 2, 'outside a scope every call projects');
                projections = 0;
                withServiceItemsScope(() => {
                  const a = getServiceItems(svc.id);
                  const b = getServiceItems(svc.id);
                  check(a === b && projections === 1, 'inside a scope the projection is reused, got ' + projections);
                  state.serviceItems[svc.id] = [...a];
                  const c = getServiceItems(svc.id);
                  check(projections === 2 && c !== a, 'replacing the items array must project again');
                  withServiceItemsScope(() => check(getServiceItems(svc.id) === c && projections === 2, 'nested scope shares the cache'));
                });
                projections = 0;
                getServiceItems(svc.id); getServiceItems(svc.id);
                check(projections === 2, 'the cache must be cleared when the outermost scope ends');
                let threw = false;
                try { withServiceItemsScope(() => { throw new Error('boom'); }); } catch { threw = true; }
                check(threw && serviceItemsScopeDepth === 0, 'a throwing render must still leave the scope');
              } finally {
                projectWorshipServiceItemsFromTemplate = previousProject;
                state.services = previousServices;
                if (previousItems === undefined) delete state.serviceItems[svc.id]; else state.serviceItems[svc.id] = previousItems;
              }
              return 'ok';
            }""")
            assert result == 'ok', result
            print('PASS source ref cache and render scope invalidation', flush=True)
            browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()

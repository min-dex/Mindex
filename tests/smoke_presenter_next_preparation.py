from smoke_app import launch_chromium, start_local_app_server, sync_playwright


server, url = start_local_app_server()
try:
    with sync_playwright() as p:
        for engine in ("chrome", "webkit"):
            browser = launch_chromium(p) if engine == "chrome" else p.webkit.launch()
            page = browser.new_page()
            page.route("**/*supabase*/**", lambda route: route.abort())
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_function("typeof prepareNextServiceFromPresenter === 'function'")
            print(engine, page.evaluate("""() => {
              const check = (value, label) => { if (!value) throw Error(label); };
              const previous = {
                services: state.services,
                serviceItems: state.serviceItems,
                selectedServiceId: state.selectedServiceId,
                selectedServiceTypeId: state.selectedServiceTypeId,
                presenter: { ...state.presenter },
              };
              const first = { id: '__next-prep-first__', type_id: 'sunday-first', date: '2099-07-05', title: '' };
              const youth = { id: '__next-prep-youth__', type_id: 'youth', date: '2099-07-05', title: '' };
              try {
                state.services = [...previous.services, first, youth];
                state.serviceItems = { ...previous.serviceItems, [first.id]: [], [youth.id]: [] };
                state.selectedServiceId = first.id;
                state.selectedServiceTypeId = first.type_id;
                state.presenter = { ...state.presenter, serviceId: first.id, viewServiceId: first.id, outputWindow: null, outputConnectedAt: 0 };
                preparePresenterService(first.id);
                const button = renderPresenterNextPreparationButton(first.id, nextPreparationTarget(first));
                check(button.includes(`data-next-service-id=\"${youth.id}\"`), 'button payload missing target');
                runPresenterAction('prepare-next-service', first.id, { nextServiceId: youth.id });
                check(state.selectedServiceId === youth.id, 'idle selection did not move');
                check(state.presenter.viewServiceId === youth.id, 'idle view did not move');
                check(state.presenter.serviceId === youth.id, 'idle presenter did not prepare target');

                state.selectedServiceId = first.id;
                state.selectedServiceTypeId = first.type_id;
                preparePresenterService(first.id);
                state.presenter.outputWindow = { closed: false };
                runPresenterAction('prepare-next-service', first.id, { nextServiceId: youth.id });
                check(state.selectedServiceId === youth.id, 'live selection did not move');
                check(state.presenter.viewServiceId === youth.id, 'live view did not move');
                check(state.presenter.serviceId === first.id, 'live output switched service');
                check(isPresenterOutputWindowOpen(), 'live output closed');
                return 'PASS next preparation links target and preserves live output';
              } finally {
                state.services = previous.services;
                state.serviceItems = previous.serviceItems;
                state.selectedServiceId = previous.selectedServiceId;
                state.selectedServiceTypeId = previous.selectedServiceTypeId;
                state.presenter = previous.presenter;
              }
            }"""), flush=True)
            browser.close()
finally:
    server.shutdown()

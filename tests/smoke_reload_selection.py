"""Reload / navigation must not move the viewed service to another one.

1. Reattaching to a live output after a reload keeps the service the user was viewing.
2. Opening another service while already in the presenter re-renders and updates the URL.
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
            page.wait_for_function("typeof restorePresenterControllerSession === 'function' && typeof openServiceInPresenter === 'function'")
            result = page.evaluate("""async () => {
              const check = (ok, message) => { if (!ok) throw new Error(message); };
              const live = { id: '__live__', type_id: 'sunday-main', date: '2026-09-13', title: '주일예배 [3부]' };
              const other = { id: '__other__', type_id: 'sunday-main', date: '2026-09-06', title: '주일예배 [3부]' };
              const saved = {
                services: state.services, serviceItems: state.serviceItems, module: state.module, selected: state.selectedServiceId,
                view: state.presenter.viewServiceId, presenterId: state.presenter.serviceId, restore: state.presenter.restorePayload,
                heartbeat: isPresenterOutputHeartbeatOpen, build: buildServicePresenterSlides, publish: publishPresenterState,
                refresh: refreshPresenterOutputConnectionState, render: render, sync: syncBrowserHistory, load: loadServiceItems,
              };
              const restore = (selected) => {
                state.services = [live, other]; state.serviceItems = { [live.id]: [{ id: 'i' }], [other.id]: [{ id: 'j' }] };
                state.module = 'presenter'; state.selectedServiceId = selected; state.presenter.viewServiceId = selected || '';
                state.presenter.serviceId = null;
                state.presenter.restorePayload = { serviceId: live.id, index: 0, slides: [{ id: 's' }] };
                return restorePresenterControllerSession();
              };
              try {
                isPresenterOutputHeartbeatOpen = () => true;
                buildServicePresenterSlides = () => [{ id: 's', type: 'title' }];
                publishPresenterState = () => {}; refreshPresenterOutputConnectionState = () => {};

                // 1a) viewing another service: attach to the live output, keep the view
                check(restore(other.id) === 'restored', 'restore should reattach');
                check(state.presenter.serviceId === live.id, 'controller must reattach to the live output');
                check(state.selectedServiceId === other.id && state.presenter.viewServiceId === other.id, 'the viewed service must not move to the live one');
                // 1b) nothing selected (bookmark without a service): adopt the live service
                check(restore(null) === 'restored' && state.selectedServiceId === live.id && state.presenter.viewServiceId === live.id, 'no selection adopts the live service');
                // 1c) already viewing the live service: unchanged
                check(restore(live.id) === 'restored' && state.selectedServiceId === live.id, 'viewing the live service stays');

                // 2) already in the presenter: render + URL sync for the newly opened service
                let renders = 0, syncs = 0;
                render = () => { renders += 1; }; syncBrowserHistory = () => { syncs += 1; }; loadServiceItems = async () => {};
                state.services = [live, other]; state.module = 'presenter'; state.selectedServiceId = live.id; state.presenter.viewServiceId = live.id;
                state.dirty.service = false;
                await openServiceInPresenter(other.id);
                check(state.selectedServiceId === other.id && state.presenter.viewServiceId === other.id, 'the newly opened service is selected');
                check(renders === 1 && syncs === 1, 'opening another service inside the presenter must render and sync the URL (' + renders + '/' + syncs + ')');
                return 'ok';
              } finally {
                state.services = saved.services; state.serviceItems = saved.serviceItems; state.module = saved.module;
                state.selectedServiceId = saved.selected; state.presenter.viewServiceId = saved.view; state.presenter.serviceId = saved.presenterId;
                state.presenter.restorePayload = saved.restore;
                isPresenterOutputHeartbeatOpen = saved.heartbeat; buildServicePresenterSlides = saved.build; publishPresenterState = saved.publish;
                refreshPresenterOutputConnectionState = saved.refresh; render = saved.render; syncBrowserHistory = saved.sync; loadServiceItems = saved.load;
              }
            }""")
            assert result == 'ok', result
            print('PASS reload keeps the viewed service; presenter navigation syncs render and URL', flush=True)
            browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()

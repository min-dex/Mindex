from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def check_flow(browser, url, engine, width, theme):
    page = browser.new_page(viewport={'width': width, 'height': 900})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.route('**/*supabase*/**', lambda route: route.abort())
    page.goto(url, wait_until='domcontentloaded')
    page.wait_for_function("typeof renderSingleVersionForms === 'function'")
    page.evaluate('''({theme}) => {
      state.module='praise';state.selectedSongId='fixture';state.selectedVersionId='v1';
      const forms=normalizeForms([
        {id:'f1',song_id:'v1',part_type:'Verse',part_number:1,sort_order:0,lyrics:'Line 1'},
        {id:'f2',song_id:'v1',part_type:'Verse',label:'Verse 2 A',sort_order:1,lyrics:'Line 2'},
        {id:'f3',song_id:'v1',part_type:'Verse',label:'Verse 2 B',sort_order:2,lyrics:'Line 3'},
      ]);
      state.songs=[{id:'fixture',title:'Editing fixture',versions:[
        {id:'v1',name:'Primary',forms}]}];
      state.forms=forms;state.dirty.forms=false;
      // A truthy client allows cached version loading; no backend is available.
      state.client={};render();
      document.body.dataset.theme=theme;
      document.body.classList.add('sidebar-collapsed');syncSidebarCollapsedState();
      window.copiedFixtureText=null;
      Object.defineProperty(navigator,'clipboard',{configurable:true,value:{
        writeText:async value=>{window.copiedFixtureText=value;}
      }});
    }''', {'theme': theme})
    assert page.evaluate("state.forms.map(displayLabel).join('|')") == 'Verse 1|Verse 2 A|Verse 2 B'
    at_labels = page.evaluate('''() => normalizeForms([
      {part_type:'Chorus',lyrics:'Original chorus'},
      {part_type:'Chorus',label:'Chorus@',lyrics:'Short chorus'},
      {part_type:'Verse',label:'Verse 1@A',lyrics:'Variant verse'},
    ]).map(displayLabel).join('|')''')
    assert at_labels == 'Chorus|Chorus@|Verse 1@A', at_labels
    at_variant_target = page.evaluate('''() => {
      const forms=normalizeForms([
        {id:'base',part_type:'Chorus',lyrics:'Original chorus'},
        {id:'variant',part_type:'Chorus',label:'Chorus@A',lyrics:'Variant chorus'},
      ]);
      return findPresenterFormForPresetLabel(forms,'C@A')?.id || '';
    }''')
    assert at_variant_target == 'variant', at_variant_target
    assert page.locator('.form-variant-input').nth(1).input_value() == 'A'
    page.locator('.form-variant-input').nth(1).fill('C')
    page.locator('.form-variant-input').nth(1).press('Tab')
    page.wait_for_function("state.forms[1].part_variant === 'C'")
    assert page.evaluate("displayLabel(state.forms[1])") == 'Verse 2 C'
    page.locator('.form-textarea').first.fill('Edited line\nSecond line')
    page.locator('.form-textarea').first.press('Tab')
    assert page.evaluate("state.forms[0].lyrics") == 'Edited line\nSecond line'
    page.locator('[data-form-action="copy"][data-index="0"]').click()
    page.wait_for_function("window.copiedFixtureText === 'Edited line\\nSecond line'")
    assert page.get_by_text('복사했어요.', exact=True).is_visible()
    page.locator('[data-form-action="down"][data-index="0"]').click()
    assert page.evaluate('state.forms[1].id') == 'f1'
    page.locator('[data-form-action="up"][data-index="1"]').click()
    assert page.evaluate('state.forms[0].id') == 'f1'
    page.locator('[data-add-form="Chorus"]').click()
    assert page.locator('.form-textarea').count() == 4
    page.locator('.form-textarea').last.fill('New chorus')
    page.locator('.form-type-select').last.select_option('Bridge')
    assert page.evaluate('state.forms[3].part_type') == 'Bridge'
    assert page.evaluate('state.forms[3].lyrics') == 'New chorus'
    page.locator('[data-form-action="delete"][data-index="3"]').click()
    assert page.locator('.form-textarea').count() == 3
    page.evaluate('''() => {
      writeFormsToSelectedVersion();
      state.songs[0].versions.push({id:'v2',name:'Secondary',forms:[
        {id:'other',song_id:'v2',part_type:'Chorus',sort_order:0,lyrics:'Other version'}]});
      render();
    }''')
    assert page.evaluate("state.songs[0].versions[0].forms[1].label") == 'Verse 2 C'
    page.locator('.version-compare-column .version-picker[data-version-id="v2"]').first.click()
    page.wait_for_function("state.selectedVersionId==='v2' && state.forms.length===1")
    assert page.locator('.form-textarea').first.input_value() == 'Other version'
    page.locator('.version-compare-column .version-picker[data-version-id="v1"]').first.click()
    page.wait_for_function("state.selectedVersionId==='v1' && state.forms.length===3")
    assert page.locator('.form-textarea').first.input_value() == 'Edited line\nSecond line'
    assert page.evaluate('state.dirty.forms')
    assert not errors, errors
    page.screenshot(path=f'/tmp/praise-editing-{engine}-{theme}-{width}.png')
    print('PASS editing flow', engine, theme, width, flush=True)
    page.close()


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as p:
            for engine in ('chromium', 'webkit'):
                browser = launch_chromium(p) if engine == 'chromium' else p.webkit.launch()
                try:
                    for theme in ('light', 'dark'):
                        for width in (1440, 390):
                            check_flow(browser, url, engine, width, theme)
                finally:
                    browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()

"""One sermon owns one citation element, regardless of legacy slot suffixes."""

from smoke_app import launch_chromium, start_local_app_server, sync_playwright


def main():
    server, url = start_local_app_server()
    try:
        with sync_playwright() as playwright:
            browser = launch_chromium(playwright)
            page = browser.new_page()
            page.goto(url)
            page.wait_for_function("typeof collapseLegacyPresenterCitationItems === 'function'")
            result = page.evaluate("""() => {
              const citation = (id, slot, reference, translationId) => ({
                id, label:'인용 구절', raw_title:reference,
                _worshipSectionId:'sermon-section', _worshipSectionKey:'sermon', _worshipSlotKey:slot,
                memo:serializeServiceItemMemo({elementType:'scripture_body',inputMode:'scripture',scriptureReferences:[reference],scriptureReferencePayloads:[{reference,scriptureTranslationId:translationId}]}),
              });
              const collapsed=collapseLegacyPresenterCitationItems([
                citation('citation-1','sermon.citation.1','마태복음 5:7','translation-a'),
                citation('citation-2','sermon.citation.2','요한복음 3:16','translation-b'),
              ]);
              if(collapsed.length!==1) throw Error('duplicate citations remain: '+collapsed.length);
              const item=collapsed[0], memo=parseServiceItemMemo(item.memo);
              const refs=serviceItemScriptureReferences(item,memo);
              if(item._worshipSlotKey!=='sermon.citation.1' || refs.join('|')!=='마태복음 5:7|요한복음 3:16' || memo.scriptureReferencePayloads.length!==2) throw Error('citation merge lost state: '+JSON.stringify({item,memo,refs}));
              return {count:collapsed.length,slot:item._worshipSlotKey,references:refs};
            }""")
            if result != {"count": 1, "slot": "sermon.citation.1", "references": ["마태복음 5:7", "요한복음 3:16"]}:
                raise RuntimeError(result)
            print("PASS citation canonicalization", result)
            browser.close()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()

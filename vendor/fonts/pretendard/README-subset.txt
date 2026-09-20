MindexSans-Common.woff2 is a Modified Version of PretendardVariable.woff2 made for
Mindex under the SIL Open Font License 1.1 (see LICENSE.txt in this directory).

- Contents: Latin, punctuation, symbols, and the 2,350 KS X 1001 Hangul syllables plus
  every non-ASCII character used by the app's UI source. Variable weight axis and layout
  features are kept.
- The internal font names were changed to "MindexSans" because the Reserved Font Name
  "Pretendard" may not be used by a Modified Version. The unmodified
  PretendardVariable.woff2 stays alongside it and is fetched only for characters the
  subset does not contain (CSS unicode-range in styles.css).
- Regenerate with the recipe in the commit that added this file (fontTools subsetter).

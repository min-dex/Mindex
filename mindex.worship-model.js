// Pure worship-domain rules shared by service loading, editing, and presenter preparation.
// Keep these functions global for the current classic-script runtime; callers in app.js keep
// their existing names while the model is extracted incrementally.
const WORSHIP_SERVICE_TYPE_ALIASES = {
  sun_1st: "sunday-first",
  sun_2nd: "sunday-second",
  sun_3rd: "sunday-main",
  sun_4th: "sunday-afternoon",
  sunday_4th: "sunday-afternoon",
  "sunday-fourth": "sunday-afternoon",
  sunday_fourth: "sunday-afternoon",
  sunday_afternoon: "sunday-afternoon",
  "주일예배": "sunday-main",
  "주일예배 [1부]": "sunday-first",
  "주일예배 (1부)": "sunday-first",
  "주일예배 [2부]": "sunday-second",
  "주일예배 (2부)": "sunday-second",
  "주일예배 [3부]": "sunday-main",
  "주일예배 (3부)": "sunday-main",
  "주일오후예배": "sunday-afternoon",
  "주일예배 [4부]": "sunday-afternoon",
  "주일예배 (4부)": "sunday-afternoon",
  wed: "wednesday",
  "수요예배": "wednesday",
  fri: "friday",
  "금요기도회": "friday",
  "월삭예배": "monthly",
  young_adult: "young-adult",
  "어린이부 예배": "children",
  nursery: "nursery",
  kindergarten: "nursery",
  preschool: "nursery",
  "유치부": "nursery",
  "유치부 예배": "nursery",
  "청소년부 예배": "youth",
  "청년부 예배": "young-adult",
  holy_week_dawn: "holy-week-dawn",
  "특별새벽기도회": "holy-week-dawn",
  "특별예배": "special",
};

const WORSHIP_SLOT_KEYS = new Set([
  "ready.waiting",
  "prayer.silent",
  "faith.creed",
  "confession.prayer",
  "confession.assurance",
  "praise.welcome",
  "praise.main",
  "praise.entrance",
  "prayer.representative",
  "word.reading",
  "word.body",
  "hymn.main",
  "special.song",
  "sermon.title",
  "sermon.scripture",
  "sermon.citation",
  "sermon.media",
  "sermon.live_scripture",
  "response.song",
  "response.prayer",
  "prayer.corporate.song",
  "prayer.meeting.free",
  "offering.praise",
  "offering.special",
  "offering.media",
  "offering.prayer",
  "announcements.main",
  "announcements.department",
  "announcements.media",
  "announcements.new_family",
  "new_family.welcome",
  "sending.doxology",
  "sending.benediction",
  "sending.lords_prayer",
  "closing.visual",
  "closing.hymn",
  "community.confession",
  "fellowship.person",
]);

function normalizeWorshipSlotKey(value = "") {
  const text = String(value || "").trim();
  if (!text) return "";
  if (/^praise\.song\.[1-9]\d*$/.test(text)) return text;
  if (text === "sermon.citation") return text;
  if (/^prayer\.corporate\.[1-9]\d*$/.test(text)) return text;
  if (/^prayer\.meeting\.song\.[1-9]\d*$/.test(text)) return text;
  return WORSHIP_SLOT_KEYS.has(text) ? text : "";
}

function explicitWorshipSlotKey(...sources) {
  for (const source of sources) {
    if (!source || typeof source !== "object") continue;
    const slotKey = normalizeWorshipSlotKey(source.slotKey || source.slot_key);
    if (slotKey) return slotKey;
  }
  return "";
}

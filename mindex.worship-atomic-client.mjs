import { createWorshipStore } from './mindex.worship-store.mjs';

const clone = value => JSON.parse(JSON.stringify(value));
const ignored = new Set(['id', 'service_id', 'section_id', 'created_at', 'updated_at']);
const jsonFields = new Set(['asset', 'config', 'source_ref', 'content_state']);
const protectedSourceKeys = ['mindexServiceDocument', 'mindexServiceDocumentHistory'];
const equal = (a, b) => JSON.stringify(a) === JSON.stringify(b);

function index(rows) {
  const result = new Map();
  for (const row of rows) {
    if (!row.id || result.has(row.id)) throw new Error('DUPLICATE_OR_MISSING_ROW_ID');
    result.set(row.id, row);
  }
  return result;
}

function change(row, previous = {}) {
  const patch = {}, removeKeys = {};
  for (const [key, value] of Object.entries(row)) {
    if (ignored.has(key) || equal(value, previous[key])) continue;
    patch[key] = value;
    if (jsonFields.has(key)) {
      if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('INVALID_JSON_PATCH');
      const removed = Object.keys(previous[key] || {}).filter(name => !Object.hasOwn(value, name));
      if (removed.length) removeKeys[key] = removed;
    }
  }
  return {id: row.id, patch, ...(Object.keys(removeKeys).length ? {removeKeys} : {})};
}

// rows are complete, already validated editor rows. A partial save supplies only
// its target rows; missing rows never become deletes without explicit IDs.
export function prepareWorshipRowsCommit({baseline, rows, metadata = {}, document,
  deleteElementIds = [], deleteSectionIds = []}) {
  if (!baseline?.service?.id) throw new Error('BASELINE_REQUIRED');
  const serviceId = baseline.service.id;
  const sections = index(baseline.sections), elements = index(baseline.elements);
  const nextSections = index(rows.sections), nextElements = index(rows.elements);
  for (const [ids, existing, next] of [[deleteSectionIds, sections, nextSections], [deleteElementIds, elements, nextElements]]) {
    if (!Array.isArray(ids) || new Set(ids).size !== ids.length
      || ids.some(id => !existing.has(id) || next.has(id))) throw new Error('INVALID_STRUCTURE_INTENT');
  }
  for (const row of nextSections.values()) {
    if (row.service_id !== serviceId) throw new Error('ROW_OWNERSHIP');
  }
  for (const row of nextElements.values()) {
    if ((!sections.has(row.section_id) && !nextSections.has(row.section_id))
      || deleteSectionIds.includes(row.section_id)) throw new Error('ROW_OWNERSHIP');
  }
  const metadataPatch = clone(metadata);
  for (const key of ['service_type_id', 'service_date']) {
    if (metadataPatch[key] === baseline.service[key]) delete metadataPatch[key];
  }
  if (metadataPatch.source_ref) {
    for (const key of protectedSourceKeys) delete metadataPatch.source_ref[key];
  }
  const sectionWrites = rows.sections.map(row => change(row, sections.get(row.id)));
  const elementWrites = rows.elements.map(row => ({...change(row, elements.get(row.id)), sectionId:row.section_id}));
  return {
    serviceId, expectedRevision:baseline.revision, metadataPatch, document:clone(document),
    sectionPatches:sectionWrites.filter(row => sections.has(row.id) && Object.keys(row.patch).length),
    newSections:sectionWrites.filter(row => !sections.has(row.id)),
    elementPatches:elementWrites.filter(row => elements.has(row.id) && Object.keys(row.patch).length)
      .map(({sectionId, ...row}) => row),
    newElements:elementWrites.filter(row => !elements.has(row.id)),
    elementMoves:rows.elements.filter(row => elements.has(row.id) && elements.get(row.id).section_id !== row.section_id)
      .map(row => ({id:row.id, sectionId:row.section_id})),
    deleteElementIds:[...deleteElementIds], deleteSectionIds:[...deleteSectionIds],
  };
}

export function prepareWorshipRowsCreate({service, rows, document}) {
  const sid = service.id;
  const sections = index(rows.sections), elements = index(rows.elements);
  if (!sid || [...sections.values()].some(row => row.service_id !== sid)
    || [...elements.values()].some(row => !sections.has(row.section_id))) throw new Error('ROW_OWNERSHIP');
  const metadataPatch = change(service).patch;
  delete metadataPatch.service_type_id;
  delete metadataPatch.service_date;
  if (metadataPatch.source_ref) {
    metadataPatch.source_ref = {...metadataPatch.source_ref};
    for (const key of protectedSourceKeys) delete metadataPatch.source_ref[key];
  }
  return clone({serviceId:sid,serviceTypeId:service.service_type_id,serviceDate:service.service_date,
    metadataPatch,document,
    sections:rows.sections.map(row => change(row)),
    elements:rows.elements.map(row => ({...change(row),sectionId:row.section_id})),
  });
}

export function createWorshipAtomicClient({rpc, journal, namespace = '', makeId = () => crypto.randomUUID()}) {
  const store = createWorshipStore({rpc, journal, makeId, methods:{
    save:'save_worship_service_v1', create:'create_worship_service_v1', delete:'delete_worship_service_v1',
  }});
  const reloadRequired = new Set();
  const reject = (id, error) => {
    // Only an actual SQLSTATE proves that PostgREST rolled back the transaction.
    if (/^(P0001|22\w{3}|23\w{3}|42501|55P03|57014|40\w{3})$/.test(error?.code || '')) {
      const failed = store.pending(id);
      if (failed) store.resolvePending(id, failed.request.requestId);
      if (/REVISION_CONFLICT/.test(error.message || '')) reloadRequired.add(id);
    }
    throw error;
  };
  return {
    creationId(identity) {
      const key = `mindex.atomic.creation.v1:${namespace}:${JSON.stringify(identity)}`;
      let id = journal.getItem(key);
      if (!id) { id = makeId(); journal.setItem(key, id); }
      return id;
    },
    finishCreation(identity, id) {
      const key = `mindex.atomic.creation.v1:${namespace}:${JSON.stringify(identity)}`;
      if (journal.getItem(key) === id) journal.removeItem(key);
    },
    baseline:id => store.baseline(id)?.aggregate || null,
    pending:id => store.pending(id),
    async read(id, {adopt = true} = {}) {
      const result = await rpc('get_worship_service_v1', {sid:id});
      if (result.error) throw result.error;
      if (!(typeof adopt === 'function' ? adopt() : adopt)) return clone(result.data);
      store.acceptRead(id, result.data);
      reloadRequired.delete(id);
      return store.baseline(id).aggregate;
    },
    async create(input) {
      const payload = prepareWorshipRowsCreate(input);
      const id = payload.serviceId;
      const pending = store.pending(id);
      if (pending && pending.operation !== 'create') throw new Error('PENDING_REQUEST_REQUIRES_RESOLUTION');
      try {
        const receipt = pending ? await store.retry(id) : await store.save('create', payload);
        const previous = pending && {...pending.request};
        if (previous) { delete previous.requestId; delete previous.protocolVersion; }
        const comparable = value => {
          const copy = clone(value);
          if (copy.document) delete copy.document.updatedAt;
          return copy;
        };
        if (receipt.deleted || receipt.aggregate?.revision !== receipt.committedRevision
          || (previous && !equal(comparable(previous), comparable(payload)))) {
          reloadRequired.add(id);
          throw new Error('ATOMIC_RETRY_COMMITTED_RELOAD_REQUIRED');
        }
        return receipt.aggregate;
      } catch (error) { reject(id, error); }
    },
    async remove(id) {
      const pending = store.pending(id);
      if (pending && pending.operation !== 'delete') throw new Error('PENDING_REQUEST_REQUIRES_RESOLUTION');
      if (reloadRequired.has(id)) throw new Error('ATOMIC_RELOAD_REQUIRED');
      const baseline = store.baseline(id);
      if (!pending && baseline?.deleted) return true;
      if (!pending && !baseline) throw new Error('BASELINE_REQUIRED');
      try {
        const receipt = pending ? await store.retry(id) : await store.save('delete', {
          serviceId:id,expectedRevision:baseline.revision,confirmDelete:true,
        });
        if (receipt.deleted !== true || receipt.aggregate !== null) throw new Error('INVALID_RECEIPT');
        return true;
      } catch (error) { reject(id, error); }
    },
    async commit(input) {
      const id = input.serviceId;
      if (reloadRequired.has(id)) throw new Error('ATOMIC_RELOAD_REQUIRED');
      const pending = store.pending(id);
      if (pending) {
        // An uncertain earlier request is resolved first. Its receipt must never
        // acknowledge the newer draft submitted by this click.
        try { await store.retry(id); } catch (error) { reject(id, error); }
        reloadRequired.add(id);
        throw new Error('ATOMIC_RETRY_COMMITTED_RELOAD_REQUIRED');
      }
      const payload = prepareWorshipRowsCommit({...input, baseline:store.baseline(id)?.aggregate});
      try {
        const receipt = await store.save('save', payload);
        if (receipt.deleted || receipt.aggregate?.revision !== receipt.committedRevision) {
          reloadRequired.add(id);
          throw new Error('ATOMIC_RELOAD_REQUIRED');
        }
        return receipt.aggregate;
      } catch (error) {
        // PostgreSQL errors roll back the RPC transaction. Transport errors do
        // not prove rollback and retain the durable request for exact retry.
        reject(id, error);
      }
    },
  };
}

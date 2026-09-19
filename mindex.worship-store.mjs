// Staged transport, deliberately not loaded by index.html before RPC cutover.
const clone = value => JSON.parse(JSON.stringify(value));
const revision = value => {
  if (typeof value !== 'string' || !/^(0|[1-9][0-9]*)$/.test(value)) throw new Error('INVALID_REVISION');
  return BigInt(value);
};

// journal must be tab-scoped (e.g. sessionStorage), not shared localStorage.
export function createWorshipStore({ rpc, journal, methods, namespace = '', makeId = () => crypto.randomUUID() }) {
  const baselines = new Map();
  const running = new Set();
  const legacyKey = id => `mindex.atomic.pending.v1:${id}`;
  const key = id => namespace ? `mindex.atomic.pending.v2:${JSON.stringify([namespace,id])}` : legacyKey(id);
  const getPending = id => {
    const raw = journal.getItem(key(id));
    if (!raw) {
      // An unscoped request cannot safely be assigned to the current project.
      if (namespace && journal.getItem(legacyKey(id))) throw new Error('PENDING_PROJECT_UNKNOWN');
      return null;
    }
    const entry = JSON.parse(raw);
    if (entry.request?.serviceId !== id || !Object.hasOwn(methods, entry.operation) || !entry.request.requestId) {
      throw new Error('INVALID_PENDING_REQUEST');
    }
    return entry;
  };
  const remember = (id, receipt) => {
    const next = receipt.aggregate;
    const rev = next ? revision(next.revision) : revision(receipt.currentRevision);
    if (rev < revision(receipt.committedRevision) || (next && receipt.deleted === true)) throw new Error('INVALID_RECEIPT');
    if (next && next.service?.id !== id) throw new Error('RECEIPT_SERVICE_MISMATCH');
    if (!next && receipt.deleted !== true) throw new Error('INVALID_RECEIPT');
    const previous = baselines.get(id);
    if (!previous || rev >= revision(previous.revision)) {
      baselines.set(id, { revision:rev.toString(), aggregate:clone(next), deleted:receipt.deleted === true });
    }
  };
  const retry = async id => {
    if (running.has(id)) throw new Error('SAVE_IN_PROGRESS');
    const entry = getPending(id);
    if (!entry) throw new Error('NO_PENDING_REQUEST');
    running.add(id);
    try {
      // A new clone prevents an RPC adapter mutating the durable retry payload.
      const result = await rpc(methods[entry.operation], { req:clone(entry.request) });
      if (result.error) throw result.error;
      const receipt = result.data;
      if (!receipt || typeof receipt.replayed !== 'boolean') throw new Error('INVALID_RECEIPT');
      revision(receipt.committedRevision);
      remember(id, receipt);
      // Do not clear another tab's newer request, even when this response arrives late.
      const current = getPending(id);
      if (current?.request.requestId === entry.request.requestId) journal.removeItem(key(id));
      return clone(receipt);
    } finally { running.delete(id); }
  };
  return {
    pending:id => clone(getPending(id)),
    baseline:id => baselines.has(id) ? clone(baselines.get(id)) : null,
    acceptRead(id, aggregate) {
      if (!aggregate) throw new Error('SERVICE_NOT_FOUND');
      remember(id, {aggregate, committedRevision:aggregate.revision, deleted:false});
    },
    async save(operation, payload) {
      if (!Object.hasOwn(methods, operation) || typeof methods[operation] !== 'string') throw new Error('INVALID_OPERATION');
      const id = payload.serviceId;
      if (!id || getPending(id)) throw new Error('PENDING_REQUEST_REQUIRES_RESOLUTION');
      const request = clone({...payload, protocolVersion:1, requestId:makeId()});
      if (operation !== 'create') {
        revision(request.expectedRevision);
        const base = baselines.get(id);
        if (!base || base.deleted || base.revision !== request.expectedRevision) throw new Error('BASELINE_REQUIRED');
      }
      // Journal failure must stop the save before contacting the server.
      journal.setItem(key(id), JSON.stringify({operation,request}));
      return retry(id);
    },
    retry,
    resolvePending(id, requestId) {
      // UI must first resolve conflict/uncertain outcome and preserve the draft.
      if (running.has(id)) throw new Error('SAVE_IN_PROGRESS');
      const entry = getPending(id);
      if (!entry || entry.request.requestId !== requestId) throw new Error('REQUEST_ID_MISMATCH');
      journal.removeItem(key(id));
    },
  };
}

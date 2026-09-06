"""Review-only label completion; never modifies the registry approval ledger."""
from copy import deepcopy
import hashlib
import json

def enrich(rows, meta, baseline, supplements):
    rows, meta, baseline = deepcopy(rows), deepcopy(meta), deepcopy(baseline)
    if baseline.get('schema') != 'raskovnik-language-review-v5':
        raise ValueError('Expected the current exported review schema')
    original_digest = hashlib.sha256(json.dumps(baseline,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    additions = []
    for row in rows:
        key = row['recordType']+':'+row['id']
        saved = baseline['review'].get(key)
        provided = supplements['labels'].get(key,{})
        for lang,suffix in [('sr','Sr'),('de','De')]:
            field, proposed = 'label'+suffix, 'proposedLabel'+suffix
            # An explicit saved blank is eligible for completion; nonblank edits win.
            current = saved['values'].get(field,'') if saved else row.get(proposed,'')
            if current:
                row[proposed] = current
                continue
            if not provided.get(lang):
                continue
            row[proposed] = provided[lang]
            if saved:
                saved['values'][field] = provided[lang]
            record = dict(key=key,language=lang,value=provided[lang],method=provided['method'],source=provided['source'],note=provided['note'])
            additions.append(record)
            row.setdefault('labelSupplementProvenance',[]).append(record)
    meta.update(seedReview=baseline['review'],seedImports=baseline.get('imports',[]),labelSupplements=additions,labelExceptions=supplements['exceptions'],reviewBaselineSha256=original_digest)
    return rows, meta

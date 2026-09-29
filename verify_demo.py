import json
from pathlib import Path
from app.experiments import contention,crash_recovery
if __name__=='__main__':
    result={'contention':contention(),'crash_recovery':crash_recovery()}
    assert result['contention']['accepted']==10
    assert result['contention']['balanced']
    assert result['crash_recovery']['inbox_rows_after']==1
    assert result['crash_recovery']['stale_ack_rejected']
    Path('results').mkdir(exist_ok=True)
    Path('results/orderops-evidence.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

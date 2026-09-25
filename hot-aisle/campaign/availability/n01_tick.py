"""N01's scheduler delegates the authorized campaign check to the key's seat."""
import argparse
import datetime as dt
import json
import os
import subprocess
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text(encoding='utf-8'))
    state = Path(cfg['state_dir'])
    state.mkdir(parents=True, exist_ok=True)
    current = dt.datetime.now(dt.timezone.utc)
    root = Path(cfg['peer_control']).expanduser()
    sys.path.insert(0, str(root))
    import estate_peer as ep
    registry = ep.load_registry(root/'estate_peer_registry.json')
    generated, _ = ep.write_artifacts(registry, ep.DEFAULT_RUNTIME)
    command = [cfg['seat_python'], '-B', cfg['seat_script'], '--config', cfg['seat_config']]
    script = ep.powershell_invocation(command)
    if (state/'STOP').exists():
        stop = "from pathlib import Path; Path(" + repr(cfg['seat_state_dir']) + ").joinpath('STOP').touch()"
        script = ep.powershell_invocation([cfg['seat_python'], '-c', stop]) + '\n' + script
    result = ep.run_peer_script(cfg['seat_peer'], script, registry, generated, timeout_seconds=135)
    result['observed_utc'] = current.isoformat()
    if result.get('ok'):
        try:
            result['campaign'] = json.loads(result['stdout'])
            del result['stdout']
        except ValueError:
            result['ok'] = False
            result['classification'] = 'INVALID_CAMPAIGN_RESPONSE'
    campaign = result.get('campaign', {})
    if campaign.get('status') in ('expired', 'stopped') or (
        current >= dt.datetime.fromisoformat(cfg['expires_utc']) and
        campaign.get('status') == 'allocation_closed'
    ):
        # Do not disable recovery merely because acquisition authorization expired.
        subprocess.run(['systemctl', '--user', 'stop', cfg['timer_unit']],
                       capture_output=True, timeout=15)
        result['timer_stop_requested'] = True
    temporary = state/'latest.tmp'
    temporary.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    os.replace(temporary, state/'latest.json')
    with (state/'ticks.jsonl').open('a', encoding='utf-8') as output:
        output.write(json.dumps(result)+'\n')
    print(json.dumps(result))
    return 1 if result.get('ok') is False else 0


if __name__ == '__main__':
    raise SystemExit(main())

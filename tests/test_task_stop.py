import subprocess
import sys
import time
from unittest.mock import Mock, patch

import pytest

from tests.test_web import client, account, material, publish


@pytest.mark.parametrize(('receipt','expected'), [
    ({}, 'cancelled'),
    ({'attempted':True}, 'unknown'),
    ({'attempted':True,'confirmed':True}, 'succeeded'),
])
def test_stop_reads_latest_receipt_after_worker_exits(client, receipt, expected):
    media, user = material(client), account(client)
    task = publish(client, media, user).json()['tasks'][0]
    store = client.app_store
    store.claim(task['id'])
    runtime = client.app.state.runtime
    process = Mock()
    runtime.processes[task['id']] = (process, task, time.monotonic())
    def stop(process):
        assert store.busy('account', user['id'])
        store.update(task['id'], result=receipt)
    with patch.object(runtime, '_stop_process', side_effect=stop) as stopper:
        result = client.post(f"/api/v2/tasks/{task['id']}/cancel")
        assert result.status_code == 204, result.text
        stopper.assert_called_once_with(process)
    assert task['id'] not in runtime.processes
    assert store.get(task['id'])['status'] == expected
    assert not store.busy('account', user['id'])
    if expected == 'unknown':
        assert client.post(f"/api/v2/tasks/{task['id']}/retry").status_code == 409


def test_stop_really_ends_worker_before_releasing_account(client):
    user = account(client)
    store = client.app_store
    task_id = store.create('check','测试进程',{},account_id=user['id'])
    store.claim(task_id)
    process = subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],start_new_session=sys.platform!='win32')
    runtime = client.app.state.runtime
    runtime.processes[task_id] = (process, store.get(task_id), time.monotonic())
    try:
        assert client.post(f'/api/v2/tasks/{task_id}/cancel').status_code == 204
        assert process.poll() is not None
        assert store.get(task_id)['status'] == 'cancelled'
        assert not store.busy('account', user['id'])
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)


def test_stop_preserves_completion_while_worker_is_being_stopped(client):
    store = client.app_store
    task_id = store.create('download','下载',{})
    store.claim(task_id)
    runtime = client.app.state.runtime
    runtime.processes[task_id] = (Mock(), store.get(task_id), time.monotonic())
    with patch.object(runtime, '_stop_process', side_effect=lambda p: store.update(task_id,status='succeeded',result={'materialId':123})):
        assert client.post(f'/api/v2/tasks/{task_id}/cancel').status_code == 204
    assert store.get(task_id)['status'] == 'succeeded'
    assert store.get(task_id)['result']['materialId'] == 123


def test_stop_requires_csrf_and_refuses_unmanaged_running_task(client):
    store=client.app_store
    task_id=store.create('publish','任务',{})
    store.claim(task_id)
    assert client.post(f'/api/v2/tasks/{task_id}/cancel',headers={'X-SAU-Token':'wrong'}).status_code == 403
    assert client.post(f'/api/v2/tasks/{task_id}/cancel').status_code == 409
    assert store.get(task_id)['status'] == 'running'


@pytest.mark.parametrize('failure', ['raises', 'still_running'])
def test_failed_stop_keeps_account_busy_and_process_tracked(client, failure):
    user = account(client)
    store = client.app_store
    task_id = store.create('check', '停止失败', {}, account_id=user['id'])
    store.claim(task_id)
    runtime = client.app.state.runtime
    process = Mock()
    process.poll.return_value = None
    runtime.processes[task_id] = (process, store.get(task_id), time.monotonic())
    with patch.object(runtime, '_stop_process', side_effect=OSError('stop failed') if failure == 'raises' else None):
        assert client.post(f'/api/v2/tasks/{task_id}/cancel').status_code == 409
    assert store.get(task_id)['status'] == 'running'
    assert store.busy('account', user['id'])
    assert task_id in runtime.processes

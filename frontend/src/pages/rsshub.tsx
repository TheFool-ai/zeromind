import {useMutation, useQuery, useQueryClient} from "@tanstack/react-query";
import {useState, type FormEvent} from "react";

import {api, type RSSHubInstance} from "../api/client";
import {Empty, ErrorNotice, PageHeader, Panel, Status} from "../components";

type InstancePayload = {
  name: string;
  base_url: string;
  authentication_mode: "key" | "code";
  enabled: boolean;
  access_key?: string | null;
};

function formPayload(form: HTMLFormElement): InstancePayload {
  const data = new FormData(form);
  return {
    name: String(data.get("name")),
    base_url: String(data.get("base_url")),
    authentication_mode: String(data.get("authentication_mode")) as "key" | "code",
    enabled: data.get("enabled") === "on"
  };
}

export function RSSHubPage() {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<RSSHubInstance | null>(null);
  const instances = useQuery({
    queryKey: ["rsshub-instances"],
    queryFn: () => api<{items: RSSHubInstance[]}>("/rsshub/instances")
  });
  const refresh = () =>
    queryClient.invalidateQueries({queryKey: ["rsshub-instances"]});
  const create = useMutation({
    mutationFn: (payload: InstancePayload) =>
      api<RSSHubInstance>("/rsshub/instances", {
        method: "POST",
        body: JSON.stringify(payload)
      }),
    onSuccess: refresh
  });
  const update = useMutation({
    mutationFn: ({id, payload}: {id: string; payload: InstancePayload}) =>
      api<RSSHubInstance>(`/rsshub/instances/${id}`, {
        method: "PUT",
        body: JSON.stringify(payload)
      }),
    onSuccess: () => {
      setEditing(null);
      refresh();
    }
  });
  const activate = useMutation({
    mutationFn: (id: string) =>
      api<RSSHubInstance>(`/rsshub/instances/${id}/activate`, {method: "POST"}),
    onSuccess: refresh
  });
  const remove = useMutation({
    mutationFn: (id: string) =>
      api(`/rsshub/instances/${id}`, {method: "DELETE"}),
    onSuccess: refresh
  });

  function submitCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload = formPayload(event.currentTarget);
    const accessKey = new FormData(event.currentTarget).get("access_key");
    if (accessKey) payload.access_key = String(accessKey);
    create.mutate(payload);
    event.currentTarget.reset();
  }

  function submitUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editing) return;
    const data = new FormData(event.currentTarget);
    const payload = formPayload(event.currentTarget);
    const accessKey = String(data.get("access_key") ?? "");
    if (accessKey) {
      payload.access_key = accessKey;
    } else if (data.get("clear_access_key") === "on") {
      payload.access_key = null;
    }
    update.mutate({id: editing.id, payload});
  }

  const mutationError =
    create.error ?? update.error ?? activate.error ?? remove.error;

  return (
    <>
      <PageHeader
        eyebrow="RSSHUB ROUTING"
        title="RSSHub 实例"
        description="注册可用实例并选择一个活动实例。rsshub:// 订阅会在抓取时由服务端完成解析和鉴权。"
      />
      <div className="split">
        <Panel title="添加实例">
          <form className="form-stack" onSubmit={submitCreate}>
            <label>实例名称<input name="name" required placeholder="Primary" /></label>
            <label>
              Base URL
              <input
                name="base_url"
                type="url"
                required
                placeholder="https://rsshub.example.com"
              />
            </label>
            <label>
              Access Key（可选）
              <input name="access_key" type="password" autoComplete="new-password" />
            </label>
            <label>
              鉴权模式
              <select name="authentication_mode" defaultValue="key">
                <option value="key">key</option>
                <option value="code">code (MD5)</option>
              </select>
            </label>
            <label className="check-label">
              <input name="enabled" type="checkbox" defaultChecked />
              启用实例
            </label>
            <button disabled={create.isPending}>添加实例</button>
          </form>
        </Panel>
        <Panel title="选择规则">
          <div className="form-stack">
            <p className="lede compact-lede">
              第一个启用的实例会自动成为活动实例。切换后，所有 rsshub://
              订阅都会使用新的实例；暂不自动故障转移。
            </p>
            <div className="notice success">
              Access Key 加密保存，页面和接口都不会回显。
            </div>
          </div>
        </Panel>
      </div>

      {mutationError ? <ErrorNotice error={mutationError} /> : null}

      {editing ? (
        <Panel title={`编辑 ${editing.name}`} className="edit-panel">
          <form
            key={editing.id}
            className="form-stack instance-edit-form"
            onSubmit={submitUpdate}
          >
            <label>
              编辑实例名称
              <input name="name" required defaultValue={editing.name} />
            </label>
            <label>
              编辑 Base URL
              <input
                name="base_url"
                type="url"
                required
                defaultValue={editing.base_url}
              />
            </label>
            <label>
              新 Access Key（留空则保持）
              <input name="access_key" type="password" autoComplete="new-password" />
            </label>
            {editing.has_access_key ? (
              <label className="check-label">
                <input name="clear_access_key" type="checkbox" />
                清除已保存的 Access Key
              </label>
            ) : null}
            <label>
              编辑鉴权模式
              <select
                name="authentication_mode"
                defaultValue={editing.authentication_mode}
              >
                <option value="key">key</option>
                <option value="code">code (MD5)</option>
              </select>
            </label>
            <label className="check-label">
              <input name="enabled" type="checkbox" defaultChecked={editing.enabled} />
              启用实例
            </label>
            <div className="button-row">
              <button
                type="button"
                className="secondary"
                onClick={() => setEditing(null)}
              >
                取消
              </button>
              <button disabled={update.isPending}>保存实例</button>
            </div>
          </form>
        </Panel>
      ) : null}

      <Panel title="已注册实例">
        {instances.error ? <ErrorNotice error={instances.error} /> : null}
        {!instances.isLoading && !instances.data?.items.length ? (
          <Empty>还没有 RSSHub 实例。添加后即可抓取 rsshub:// 订阅。</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>名称</th><th>Base URL</th><th>状态</th>
                  <th>鉴权</th><th>密钥</th><th>操作</th>
                </tr>
              </thead>
              <tbody>
                {instances.data?.items.map((instance) => (
                  <tr key={instance.id}>
                    <td><strong>{instance.name}</strong></td>
                    <td><code>{instance.base_url}</code></td>
                    <td>
                      <Status
                        value={instance.active ? "活动" : instance.enabled ? "待用" : "停用"}
                      />
                    </td>
                    <td><code>{instance.authentication_mode}</code></td>
                    <td>{instance.has_access_key ? "已配置密钥" : "无密钥"}</td>
                    <td>
                      <div className="row-actions">
                        <button
                          className="tiny secondary"
                          aria-label={`设为活动实例 ${instance.name}`}
                          disabled={instance.active || !instance.enabled}
                          onClick={() => activate.mutate(instance.id)}
                        >
                          设为活动
                        </button>
                        <button
                          className="tiny secondary"
                          aria-label={`编辑 ${instance.name}`}
                          onClick={() => setEditing(instance)}
                        >
                          编辑
                        </button>
                        <button
                          className="tiny secondary"
                          aria-label={`删除 ${instance.name}`}
                          disabled={instance.active}
                          onClick={() => remove.mutate(instance.id)}
                        >
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}

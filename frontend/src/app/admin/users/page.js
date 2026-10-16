"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Search, UserRound } from "lucide-react";

import { apiRequest } from "../../../lib/api";
import { AdminEmpty, AdminError, AdminLoading, AdminPageHeader, AdminStatus, formatAdminDate } from "../../../components/admin/AdminUI";

export default function AdminUsersPage() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [actionId, setActionId] = useState("");

  async function loadUsers({ showLoading = true } = {}) {
    if (showLoading) setLoading(true);
    setError("");
    try {
      const data = await apiRequest("/admin/users");
      setUsers(Array.isArray(data?.users) ? data.users : []);
    } catch (requestError) {
      setError(requestError?.message || "Unable to load users.");
    } finally {
      if (showLoading) setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    apiRequest("/admin/users")
      .then((data) => {
        if (active) setUsers(Array.isArray(data?.users) ? data.users : []);
      })
      .catch((requestError) => {
        if (active) setError(requestError?.message || "Unable to load users.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const filteredUsers = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return users;
    return users.filter((user) =>
      [user?.name, user?.email, user?.role].some((value) =>
        String(value || "").toLowerCase().includes(query)
      )
    );
  }, [users, search]);

  async function changeBlockedState(user) {
    const action = user.is_blocked ? "unblock" : "block";
    if (action === "block" && !window.confirm(`Block ${user.name || user.email}? They will no longer be able to use the workspace.`)) {
      return;
    }

    setActionId(user.id);
    setNotice("");
    setError("");
    try {
      const result = await apiRequest(`/admin/users/${encodeURIComponent(user.id)}/${action}`, { method: "PATCH" });
      if (result?.user) {
        setUsers((current) => current.map((item) => item.id === user.id ? result.user : item));
      }
      setNotice(action === "block" ? "User blocked successfully." : "User unblocked successfully.");
      await loadUsers({ showLoading: false });
    } catch (requestError) {
      setError(requestError?.message || `Unable to ${action} this user.`);
    } finally {
      setActionId("");
    }
  }

  return (
    <div className="workspace-content admin-content">
      <AdminPageHeader title="Users" description="Review workspace accounts and manage access." />

      <section className="workspace-panel admin-panel">
        <div className="admin-list-toolbar">
          <div className="admin-list-heading">
            <div className="workspace-title-icon"><UserRound size={18} /></div>
            <div>
              <h2>All users</h2>
              <p>{users.length} accounts</p>
            </div>
          </div>
          <label className="admin-search">
            <Search size={16} />
            <span className="sr-only">Filter users by name, email, or role</span>
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Filter users…" />
          </label>
        </div>

        {notice ? <div className="admin-feedback admin-feedback-success" role="status">{notice}</div> : null}
        {error ? <AdminError message={error} onRetry={() => loadUsers()} /> : null}
        {loading ? <AdminLoading label="Loading users…" /> : null}
        {!loading && !error && users.length === 0 ? (
          <AdminEmpty title="No users found" description="There are no user accounts to display." />
        ) : null}
        {!loading && !error && users.length > 0 && filteredUsers.length === 0 ? (
          <AdminEmpty title="No matching users" description="Try a different name, email, or role." />
        ) : null}

        {!loading && !error && filteredUsers.length > 0 ? (
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead><tr>
                <th scope="col">User</th><th scope="col">Role</th><th scope="col">Verified</th>
                <th scope="col">Status</th><th scope="col">Created</th><th scope="col">Actions</th>
              </tr></thead>
              <tbody>
                {filteredUsers.map((user) => (
                  <tr key={user.id}>
                    <td data-label="User">
                      <div className="admin-user-cell"><strong>{user.name || "—"}</strong><span>{user.email || "—"}</span></div>
                    </td>
                    <td data-label="Role"><span className="admin-role">{user.role || "—"}</span></td>
                    <td data-label="Verified"><AdminStatus tone={user.is_verified ? "success" : "neutral"}>{user.is_verified ? "Verified" : "Unverified"}</AdminStatus></td>
                    <td data-label="Status"><AdminStatus tone={user.is_blocked ? "danger" : "success"}>{user.is_blocked ? "Blocked" : "Active"}</AdminStatus></td>
                    <td data-label="Created">{formatAdminDate(user.created_at)}</td>
                    <td data-label="Actions">
                      <div className="admin-row-actions">
                        <Link className="admin-action-link" href={`/admin/users/${encodeURIComponent(user.id)}`}>View details</Link>
                        <button
                          type="button"
                          className={`admin-action-button ${user.is_blocked ? "" : "admin-action-danger"}`}
                          disabled={actionId === user.id}
                          onClick={() => changeBlockedState(user)}
                        >
                          {actionId === user.id ? "Saving…" : user.is_blocked ? "Unblock" : "Block"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </div>
  );
}

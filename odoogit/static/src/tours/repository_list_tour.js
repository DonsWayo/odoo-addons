/** @odoo-module **/
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("odoogit_repository_list", {
    url: "/odoo/action-odoogit.action_git_repository",
    steps: () => [
        { trigger: ".o_list_view, .o_kanban_view", content: "View rendered", run: false },
        { trigger: "body", content: "List visible with e2e-repo", run: () => {
            const text = document.body.innerText;
            if (!text.includes("e2e-repo")) throw new Error("e2e-repo not in list");
        }},
    ],
});

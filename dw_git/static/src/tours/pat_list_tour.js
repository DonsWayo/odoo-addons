/** @odoo-module **/
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("dw_git_pat_list", {
    url: "/odoo/action-dw_git.action_git_personal_access_token",
    steps: () => [
        { trigger: ".o_list_view", content: "PAT list rendered", run: false },
        { trigger: "body", content: "e2e-token row present", run: () => {
            if (!document.body.innerText.includes("e2e-token")) throw new Error("token missing");
        }},
    ],
});

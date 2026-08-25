/** @odoo-module **/
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("dw_git_branches_tab", {
    url: "/odoo/action-dw_git.action_git_repository",
    steps: () => [
        { trigger: ".o_list_view tbody tr td:nth-child(3)", content: "Open first repo row", run: "click" },
        { trigger: ".o_form_view", content: "Form opened", run: false },
        { trigger: ".nav-link:contains('Branches')", content: "Open Branches tab", run: "click" },
        { trigger: ".o_field_one2many .o_data_row:contains('main')", content: "main branch row visible", run: false },
    ],
});

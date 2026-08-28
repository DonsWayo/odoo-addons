/** @odoo-module **/
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("dw_git_create_repo", {
    url: "/odoo/action-dw_git.action_git_repository",
    steps: () => [
        { trigger: "button.o-new-button, .o_control_panel_new button:contains('New'), button:contains('New')", content: "Click New" },
        { trigger: ".o_form_view [name='name'] input", content: "Name field", run: "edit tour-created-repo" },
        { trigger: ".o_form_button_save, button[accesskey='s']", content: "Save", run: "click" },
        { trigger: ".o_form_view .o_field_char[name='name']", content: "Saved in edit mode", run: () => {
            const el = document.querySelector(".o_field_char[name='name']");
            if (!el || el.value !== "tour-created-repo") throw new Error("save failed");
        }},
    ],
});

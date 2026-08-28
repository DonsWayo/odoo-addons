/** @odoo-module **/
import { registry } from "@web/core/registry";

/**
 * Creating a repository through the UI, the way a user does it.
 *
 * No `url` property on purpose: a tour that declares one makes the tour
 * service navigate there on start, discarding the startUrl the test passed.
 */
registry.category("web_tour.tours").add("dw_git_create_repo", {
    steps: () => [
        {
            // .o_list_button_add is the list controller's own class for the
            // New button (web/views/list/list_controller.xml). The previous
            // trigger matched on the text "New", and Odoo renders duplicate
            // control-panel buttons for different viewports — the hidden one
            // can match first, so the step timed out clicking nothing. It
            // passed under headless Chromium 131 locally and timed out under
            // Chrome 152 in CI, which is exactly the kind of difference a
            // text-matched selector invites.
            trigger: ".o_list_button_add",
            content: "Click New",
            // An explicit run. Without it the step only WAITED for the
            // button, never pressed it, so the form never opened and the
            // next step timed out looking for a field that could not exist.
            run: "click",
        },
        {
            // Odoo puts the field name on the wrapper div, not on the input,
            // so input[name='name'] matches nothing.
            trigger: ".o_form_view [name='name'] input",
            content: "Name field",
            run: "edit tour-created-repo",
        },
        {
            trigger: ".o_form_button_save, button[accesskey='s']",
            content: "Save",
            run: "click",
        },
        {
            trigger: ".o_field_char[name='name'] input",
            content: "The name persisted through the save",
            run: () => {
                // Read the INPUT. The previous version queried the wrapper
                // div and asked for its .value, which is always undefined,
                // so this assertion could only ever fail.
                const el = document.querySelector(".o_field_char[name='name'] input");
                if (!el || el.value !== "tour-created-repo") {
                    throw new Error(
                        `save failed: name is ${el ? `"${el.value}"` : "absent"}`);
                }
            },
        },
    ],
});

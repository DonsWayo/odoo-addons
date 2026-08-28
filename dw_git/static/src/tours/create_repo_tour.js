/** @odoo-module **/
import { registry } from "@web/core/registry";
import { stepUtils } from "@web_tour/tour_utils";

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
            // New button. Matching on the text "New" hit a hidden duplicate
            // control-panel button and hung under Chrome 152 in CI while
            // passing under Chromium 131 locally.
            trigger: ".o_list_button_add",
            content: "Click New",
            run: "click",
        },
        {
            // Odoo puts the field name on the wrapper div, not the input.
            trigger: ".o_form_view [name='name'] input",
            content: "Name field",
            run: "edit tour-created-repo",
        },
        // Odoo's own save helper rather than a hand-written click. It uses
        // `.o_form_button_save:enabled` and then waits for
        // `.o_form_readonly, .o_form_saved`. Clicking a bare
        // `.o_form_button_save` could land on the button while it was still
        // disabled, which does nothing — the tour then ended with the form
        // dirty and Odoo failed it: "Tour finished with a dirty form view
        // being open."
        ...stepUtils.saveForm(),
        {
            trigger: ".o_field_char[name='name'] input",
            content: "The name persisted through the save",
            run: () => {
                // Read the INPUT. Asking a wrapper div for .value gives
                // undefined, so that assertion could only ever fail.
                const el = document.querySelector(".o_field_char[name='name'] input");
                if (!el || el.value !== "tour-created-repo") {
                    throw new Error(
                        `save failed: name is ${el ? `"${el.value}"` : "absent"}`);
                }
            },
        },
    ],
});

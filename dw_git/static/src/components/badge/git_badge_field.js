/** @odoo-module **/

import { registry } from "@web/core/registry";
import { badgeField } from "@web/views/fields/badge/badge_field";

/**
 * Odoo's `badge` widget declares supportedTypes ["selection", "many2one",
 * "char"]. This module used it on twenty-three Integer and Boolean fields,
 * which produced "The widget: badge don't support the type integer" on
 * every view load.
 *
 * The warning was the smaller half of the problem. Those views also passed
 * `options="{'classes': {...}}"` colour maps, and `badge` has no `classes`
 * option at all — its only supported option is `color_field`, and colour
 * otherwise comes from `decoration-*` attributes. So every one of those
 * carefully written colour maps was silently ignored and every badge
 * rendered in the same default grey.
 *
 * Rather than drop the styling, extend the widget for the types we
 * actually use and move the colours onto `decoration-*`, which is the
 * mechanism Odoo reads.
 */
export const gitBadgeField = {
    ...badgeField,
    supportedTypes: [...badgeField.supportedTypes, "integer", "float", "boolean"],
};

registry.category("fields").add("git_badge", gitBadgeField);

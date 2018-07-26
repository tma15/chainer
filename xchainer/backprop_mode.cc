#include "xchainer/backprop_mode.h"

#include <algorithm>
#include <memory>
#include <vector>

#include <nonstd/optional.hpp>

#include "xchainer/array.h"
#include "xchainer/array_node.h"
#include "xchainer/constant.h"
#include "xchainer/context.h"
#include "xchainer/graph.h"

namespace xchainer {
namespace backprop_mode_detail {

thread_local BackpropModeStack* t_backprop_mode_stack{nullptr};

template <bool kModeFlag>
void BackpropModeScope<kModeFlag>::BackpropModeScopeImpl(const nonstd::optional<std::vector<GraphId>>& graph_ids, Context& context) {
    // The outer-most scope creates an instance of BackpropModeStack.
    if (t_backprop_mode_stack == nullptr) {
        t_backprop_mode_stack = new BackpropModeStack{};
        is_outermost_ = true;
    }

    if (graph_ids.has_value()) {
        n_ = graph_ids->size();
        for (const GraphId& graph_id : *graph_ids) {
            t_backprop_mode_stack->emplace_back(context, graph_id, kModeFlag);
        }
    } else {
        n_ = 1;
        t_backprop_mode_stack->emplace_back(context, nonstd::nullopt, kModeFlag);
    }
}

template <bool kModeFlag>
BackpropModeScope<kModeFlag>::~BackpropModeScope() {
    assert(t_backprop_mode_stack != nullptr);
    assert(t_backprop_mode_stack->size() >= n_);

    // Recover thread local variable to nullptr on exiting from the outer-most scope.
    if (is_outermost_) {
        assert(t_backprop_mode_stack->size() == n_);
        delete t_backprop_mode_stack;
        t_backprop_mode_stack = nullptr;
    } else {
        t_backprop_mode_stack->erase(t_backprop_mode_stack->end() - n_, t_backprop_mode_stack->end());
    }
}

}  // namespace backprop_mode_detail

bool IsBackpropRequired(const nonstd::optional<GraphId>& graph_id, Context& context) {
    GraphId actual_graph_id = graph_id.has_value() ? *graph_id : context.default_graph_id();
    backprop_mode_detail::BackpropModeStack* bms = backprop_mode_detail::t_backprop_mode_stack;
    if (bms == nullptr) {
        // No backprop scopes have been created and backprop is thus always required, per default.
        return true;
    }
    auto it = std::find_if(bms->rbegin(), bms->rend(), [&actual_graph_id, &context](const internal::BackpropMode& bm) {
        return &context == &bm.context() && (!bm.graph_id().has_value() || actual_graph_id == *bm.graph_id());
    });
    if (it != bms->rend()) {
        return it->backprop();
    }
    return true;  // Per default.
}

bool IsGradRequired(const Array& array, const nonstd::optional<GraphId>& graph_id) {
    GraphId actual_graph_id = graph_id.has_value() ? *graph_id : array.device().context().default_graph_id();
    if (internal::GetArrayBody(array)->HasArrayNode(actual_graph_id)) {
        return IsBackpropRequired(actual_graph_id, array.device().context());
    }
    return false;
}

bool IsGradRequired(const Array& array, AnyGraph /*any_graph*/) {
    Context& context = array.device().context();
    const std::vector<std::shared_ptr<internal::ArrayNode>>& array_nodes = internal::GetArrayBody(array)->nodes();
    return std::any_of(array_nodes.begin(), array_nodes.end(), [&context](const std::shared_ptr<const internal::ArrayNode>& array_node) {
        return IsBackpropRequired(array_node->graph_id(), context);
    });
}

}  // namespace xchainer

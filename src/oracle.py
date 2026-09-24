from __future__ import annotations

import heapq
import time
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from .cost import Cost, MaybeCost, cost_to_json
from .model import Instance


@dataclass
class OracleResult:
    status: str
    cost: MaybeCost
    events: list[dict[str, Any]]
    discovered_states: int
    expanded_states: int
    cpu_seconds: float

    def to_json(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "cost": cost_to_json(self.cost),
            "events": self.events,
            "discovered_states": self.discovered_states,
            "expanded_states": self.expanded_states,
            "cpu_seconds": self.cpu_seconds,
        }


def configuration_oracle(
    instance: Instance,
    *,
    state_cap: int = 15_000,
    cpu_cap: float = 15.0,
) -> OracleResult:
    """Dijkstra search over one-shot configurations with no subtree-order restriction."""

    node_ids = instance.order
    index = {node_id: position for position, node_id in enumerate(node_ids)}
    state_slot = {state: slot + 1 for slot, state in enumerate(instance.states)}
    slot_state = {slot + 1: state for slot, state in enumerate(instance.states)}
    root_index = index[instance.root]

    # (assigned representation slots, red bit mask, stored-in-blue bit mask)
    initial = ((0,) * len(node_ids), 0, 0)
    distance: dict[tuple[tuple[int, ...], int, int], Cost] = {initial: Cost.zero()}
    predecessor: dict[
        tuple[tuple[int, ...], int, int],
        tuple[tuple[tuple[int, ...], int, int], dict[str, Any]],
    ] = {}
    queue: list[tuple[Cost, int, tuple[tuple[int, ...], int, int]]] = []
    serial = 0
    heapq.heappush(queue, (Cost.zero(), serial, initial))
    expanded = 0
    start = time.process_time()

    def resident_memory(assigned: tuple[int, ...], red_mask: int) -> int:
        total = 0
        for position, slot in enumerate(assigned):
            if red_mask & (1 << position):
                total += instance.node(node_ids[position]).weight(slot_state[slot])
        return total

    def is_goal(config: tuple[tuple[int, ...], int, int]) -> bool:
        assigned, _red, blue = config
        if not (blue & (1 << root_index)):
            return False
        slot = assigned[root_index]
        return slot != 0 and slot_state[slot] in instance.root_states

    def push(
        current: tuple[tuple[int, ...], int, int],
        current_cost: Cost,
        successor: tuple[tuple[int, ...], int, int],
        edge_cost: Cost,
        action: dict[str, Any],
    ) -> str | None:
        nonlocal serial
        candidate = current_cost + edge_cost
        old = distance.get(successor)
        if old is None or candidate < old:
            if old is None and len(distance) >= state_cap:
                return "state_cap"
            distance[successor] = candidate
            predecessor[successor] = (current, action)
            serial += 1
            heapq.heappush(queue, (candidate, serial, successor))
        return None

    terminal: tuple[tuple[int, ...], int, int] | None = None
    terminal_status = "complete"
    while queue:
        if time.process_time() - start > cpu_cap:
            terminal_status = "cpu_cap"
            break
        current_cost, _serial, current = heapq.heappop(queue)
        if distance.get(current) != current_cost:
            continue
        expanded += 1
        if is_goal(current):
            terminal = current
            break
        assigned, red, blue = current
        memory = resident_memory(assigned, red)

        # Load an as-yet-unselected source representation.
        for position, node_id in enumerate(node_ids):
            node = instance.node(node_id)
            bit = 1 << position
            if node.kind != "source" or assigned[position] != 0 or red & bit:
                continue
            for state in sorted(node.source_states):
                size = node.weight(state)
                if memory + size > instance.capacity:
                    continue
                successor_assigned = list(assigned)
                successor_assigned[position] = state_slot[state]
                successor = (tuple(successor_assigned), red | bit, blue)
                status = push(
                    current,
                    current_cost,
                    successor,
                    Cost(size, Fraction(0, 1)),
                    {"event": "load", "node": node_id, "state": state},
                )
                if status:
                    terminal_status = status
                    queue.clear()
                    break
            if terminal_status != "complete":
                break
        if terminal_status != "complete":
            break

        # Reload a produced internal value from slow memory.
        for position, node_id in enumerate(node_ids):
            node = instance.node(node_id)
            bit = 1 << position
            if node.kind != "op" or assigned[position] == 0 or red & bit or not (blue & bit):
                continue
            state = slot_state[assigned[position]]
            size = node.weight(state)
            if memory + size > instance.capacity:
                continue
            successor = (assigned, red | bit, blue)
            status = push(
                current,
                current_cost,
                successor,
                Cost(size, Fraction(0, 1)),
                {"event": "load", "node": node_id, "state": state},
            )
            if status:
                terminal_status = status
                queue.clear()
                break
        if terminal_status != "complete":
            break

        # Store a resident produced value. A duplicate store has no useful effect.
        for position, node_id in enumerate(node_ids):
            node = instance.node(node_id)
            bit = 1 << position
            if node.kind != "op" or not (red & bit) or blue & bit:
                continue
            state = slot_state[assigned[position]]
            size = node.weight(state)
            successor = (assigned, red, blue | bit)
            status = push(
                current,
                current_cost,
                successor,
                Cost(size, Fraction(0, 1)),
                {"event": "store", "node": node_id},
            )
            if status:
                terminal_status = status
                queue.clear()
                break
        if terminal_status != "complete":
            break

        # Delete only a stored internal copy. Other deletions are one-shot dead ends.
        for position, node_id in enumerate(node_ids):
            node = instance.node(node_id)
            bit = 1 << position
            if node.kind != "op" or not (red & bit) or not (blue & bit):
                continue
            successor = (assigned, red & ~bit, blue)
            status = push(
                current,
                current_cost,
                successor,
                Cost.zero(),
                {"event": "delete", "node": node_id},
            )
            if status:
                terminal_status = status
                queue.clear()
                break
        if terminal_status != "complete":
            break

        # Atomic non-overwriting computations; operands are consumed immediately afterward.
        for position, node_id in enumerate(node_ids):
            node = instance.node(node_id)
            bit = 1 << position
            if node.kind != "op" or assigned[position] != 0:
                continue
            operand_bits = 0
            operands_present = True
            for child_id in node.operands:
                child_bit = 1 << index[child_id]
                operand_bits |= child_bit
                if not (red & child_bit):
                    operands_present = False
                    break
            if not operands_present:
                continue
            for recipe in sorted(node.recipes, key=lambda item: item.name):
                matches = True
                for child_id, required_state in zip(node.operands, recipe.inputs):
                    child_slot = assigned[index[child_id]]
                    if child_slot == 0 or slot_state[child_slot] != required_state:
                        matches = False
                        break
                if not matches:
                    continue
                output_size = node.weight(recipe.output)
                if memory + output_size > instance.capacity:
                    continue
                successor_assigned = list(assigned)
                successor_assigned[position] = state_slot[recipe.output]
                successor_red = (red & ~operand_bits) | bit
                successor = (tuple(successor_assigned), successor_red, blue)
                status = push(
                    current,
                    current_cost,
                    successor,
                    Cost(0, recipe.work),
                    {
                        "event": "compute",
                        "node": node_id,
                        "recipe": recipe.name,
                        "output": recipe.output,
                    },
                )
                if status:
                    terminal_status = status
                    queue.clear()
                    break
            if terminal_status != "complete":
                break
        if terminal_status != "complete":
            break

    elapsed = time.process_time() - start
    if terminal_status != "complete":
        return OracleResult(terminal_status, None, [], len(distance), expanded, elapsed)
    if terminal is None:
        return OracleResult("complete", None, [], len(distance), expanded, elapsed)

    events: list[dict[str, Any]] = []
    cursor = terminal
    while cursor != initial:
        previous, action = predecessor[cursor]
        events.append(action)
        cursor = previous
    events.reverse()
    return OracleResult("complete", distance[terminal], events, len(distance), expanded, elapsed)

## ADDED Requirements

### Requirement: Now pending wrap-up
A `running` card on the Now tab SHALL show `wrap-up pending since HH:MM` when the pipeline's run log has an `owner_wrap_up_requested` event after its last `dispatcher_start` and no `owner_wrap_up_done` after it; the Now API SHALL give that request time, or null.

#### Scenario: Pending wrap-up shown
- **WHEN** `alpha` is running and its run log has `owner_wrap_up_requested` at 14:05 after the last `dispatcher_start` and no `owner_wrap_up_done`
- **THEN** `alpha`'s card shows `wrap-up pending since 14:05`

#### Scenario: Wrap-up done
- **WHEN** the run log has `owner_wrap_up_done` after that request
- **THEN** the card shows no pending wrap-up

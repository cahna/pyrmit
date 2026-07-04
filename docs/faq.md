# FAQ

Design-rationale questions that come up when adopting pyrmit, especially when
migrating a Strawberry GraphQL application from `BasePermission` classes.

## Why is the Strawberry adapter a `FieldExtension` instead of a `BasePermission`?

Because the two hooks have genuinely different contracts, and authorization
needs the stronger one.

Strawberry's `BasePermission.has_permission(source, info, **kwargs) -> bool`
is a boolean gate that runs before the resolver. That contract forces every
permission class to do its own entity loading (open a session, guess which
kwarg carries the resource id, fetch the row) and then collapse the outcome
into a yes/no. In practice this breeds the pathologies pyrmit exists to
remove: per-class kwargs sniffing, duplicated lookups (the permission loads
the entity, then the resolver loads it again), and — worst — the
**split-gate existence leak**, where the permission check and the not-found
check live in different layers and answer with distinguishable errors, so a
caller can probe which resource ids exist.

A `FieldExtension` wraps the resolver call itself
(`resolve_async(next_, source, info, **kwargs)`), which lets one component
own the entire sequence: *load subject → evaluate policy → enforce the
denial surface → (maybe) run the resolver*. Several core pyrmit behaviors
are simply not expressible as a permission class:

- **Denial surfaces.** `FORBIDDEN` raises, `NOT_FOUND` raises an
  existence-concealing error, and `NULL` resolves the field to `null` with
  no error (field redaction). A boolean gate can only pass or fail.
- **Existence concealment.** Subject loading happens *inside* the guard, so
  "missing" and "denied" surface identically from the same layer. With a
  split design, the two outcomes come from different layers and leak.
- **Subscriptions.** The extension decides once, before the stream starts,
  then hands the async generator back untouched. A deny terminates the
  subscription without ever opening it.
- **Post-resolution redaction.** `post_resolution_policy_guard` decides
  against the *resolved value*. `BasePermission` has no post-resolver hook
  at all.

Two more practical reasons:

- **Dependency injection.** Strawberry instantiates permission classes
  itself, so there is no clean way to hand them an engine, a principal
  loader, or an error-mapping hook — each class ends up reaching into
  `info.context` and hand-rolling its wiring. Guard extensions are values
  *you* construct: a `PolicyGuardFactory` captures the engine, the
  principal loader, and the `deny_handler` once, and each field states only
  what varies (action, subject type, subject loader).
- **Type safety.** `permission_classes=[CanEditArticle]` binds a class name
  with no connection to the resolver's argument shape — hence runtime
  kwargs sniffing. A parameterized factory
  (`PolicyGuardFactory[PrincipalT, ActionT, SubjectT]`) makes a wrong
  `action` enum value or a subject loader returning the wrong type a mypy
  error at the decorator, not a production surprise.

## Do I still need `permission_classes` at all?

Only for **authentication**, and even that is optional.

Authentication ("is this a valid caller?") genuinely is a boolean pre-gate
with no subject to load, so `BasePermission`'s contract fits it. A common
migration endpoint keeps exactly one permission class — the app's
`AuthenticatedUser` equivalent — and moves every authorization decision
into policy guards.

It is also legitimate to drop the authentication class entirely: the
guard's `principal_loader` runs before any policy decision, so a loader
that raises the application's authentication error for anonymous callers
enforces authn as a side effect of building the principal. Either way,
keep the separation crisp: authentication lives in the context/principal
loader, authorization lives in policies. Do not re-introduce authorization
logic into permission classes alongside guards — that recreates the split
gate.

## What happens when a field has both `permission_classes` and a guard extension?

Strawberry evaluates `permission_classes` before field extensions run, so
an authentication class fires first and the pyrmit guard second — the
classic *authn → authz* order. The two compose cleanly:

```python
@strawberry.field(
    permission_classes=[AuthenticatedUser],   # authn: boolean pre-gate
    extensions=[guards.guard(                 # authz: load -> decide -> enforce
        action=Action.READ,
        subject_type=Article,
        load_subject=load_article,
    )],
)
async def article(self, article_id: int) -> ArticleType | None: ...
```

If the principal loader already rejects anonymous callers (see the previous
question), the permission class is redundant-but-harmless: it merely makes
the authn requirement visible in the decorator at the cost of a second
check.

## Is a guard call less readable than a named permission class?

Slightly, if you inline the raw `policy_guard(...)` call at every field.
The intended pattern is a small vocabulary of named helpers in one module —
the guard equivalent of the class names you are giving up:

```python
def manage_article_guard(*, kwarg: str = "article_id") -> FieldExtension:
    return guards.guard(
        action=Action.MANAGE,
        subject_type=Article,
        load_subject=article_subject_from(kwarg=kwarg),
    )
```

`extensions=[manage_article_guard()]` reads as declaratively as
`permission_classes=[CanManageArticle]` did, while remaining a real, typed,
injectable value — with the argument shape declared per field instead of
discovered by kwargs sniffing at request time.

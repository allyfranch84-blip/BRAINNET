"""Ordered execution of already validated semantic plans. No model or native IO."""
from motor_intent import validate_plan

SPECIAL=frozenset(('open_app','move_to','click_target','inspect_monitor'))


def groups(steps):
    pending=[]
    prior_named_move=False
    for step in steps:
        if step['action'] in SPECIAL:
            if pending:
                yield pending
                pending=[]
            yield [step]
            prior_named_move=step['action']=='move_to'
        elif prior_named_move and step['action']=='click':
            # The kernel re-resolves the named object instead of blindly clicking.
            yield [step]
            prior_named_move=False
        else:
            pending.append(step)
            prior_named_move=False
    if pending:
        yield pending


def execute_sequence(plan,run,*,check_active):
    validate_plan(plan)
    if plan['status']!='execute':
        raise ValueError('nonexecutable plan')
    receipts=[]
    completed=0
    total=len(plan['steps'])
    dispatched=False
    input_only=False
    any_effect=False
    failure=None
    for group in groups(plan['steps']):
        try:
            check_active()
        except Exception as exc:
            failure={'status':'CANCEL_REQUESTED','reply':str(exc),'dispatched':False}
            break
        try:
            result=run(group,tuple(receipts))
        except Exception as exc:
            # An exception in the operation is not proof that nothing was sent.
            result={'status':'EFFECT_UNVERIFIED','reply':f'Etapa interrompida ({type(exc).__name__}).','dispatched':None}
        status=result.get('status','EFFECT_UNVERIFIED')
        receipt={'start_step':completed+1,'steps':group,'status':status,'reply':result.get('reply',''),
                 'motor_results':result.get('motor_results',[]),'dispatched':result.get('dispatched')}
        receipts.append(receipt)
        if result.get('dispatched') is True:
            dispatched=True
        elif result.get('dispatched') is None and dispatched is False:
            dispatched=None
        accepted=status in ('EFFECT_VERIFIED','INPUT_SENT') or (status=='OBSERVED' and group[0]['action']=='inspect_monitor')
        if not accepted:
            failure=result
            break
        completed+=len(group)
        input_only |= status=='INPUT_SENT'
        any_effect |= status=='EFFECT_VERIFIED'
    lines=[f'Sequência: {completed}/{total} etapas confirmadas ou aceitas pelo sistema.']
    for item in receipts:
        first=item['start_step']
        last=first+len(item['steps'])-1
        label=str(first) if first==last else f'{first}-{last}'
        lines.append(f"{label}. [{item['status']}] {item['reply']}")
    if failure is not None:
        status='PARTIAL' if completed or dispatched is True else failure.get('status','EFFECT_UNVERIFIED')
        if not receipts or receipts[-1]['reply']!=failure.get('reply'):
            lines.append(str(failure.get('reply','')))
        lines.append('Sequência interrompida; etapas restantes não executadas.')
    else:
        status='INPUT_SENT' if input_only else 'EFFECT_VERIFIED' if any_effect else 'OBSERVED'
        if input_only:
            lines.append('O efeito final de cliques/rolagem no aplicativo não foi comprovado.')
    return {'status':status,'reply':'\n'.join(lines),'dispatched':dispatched,
            'completed_steps':completed,'total_steps':total,'sequence_results':receipts}

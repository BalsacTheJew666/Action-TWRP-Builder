#!/usr/bin/env python3
"""Motorola XT2615-1: READ-ONLY live-module ABI witness collection.

Compares experimental AR9271 core CRC requirements to the __versions imports
inside *already loaded* Android stock modules. A loaded module's import is
corroborating evidence, NOT an authoritative live kernel export CRC.
Does not insmod, patch, write kernel files, sign, or flash anything.
"""
import argparse, csv, json, os, shlex, struct, subprocess
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

STOCK_DIRS=('/vendor_dlkm/lib/modules','/system_dlkm/lib/modules',
            '/odm_dlkm/lib/modules','/vendor/lib/modules','/system/lib/modules',
            '/odm/lib/modules','/lib/modules')
CANDIDATE_VERMAGIC='5.15.180-MMI-W1WN36.18-114-dirty SMP preempt mod_unload modversions aarch64'

def read(path):
    try:
        return Path(path).read_bytes()
    except OSError:
        try:
            result=subprocess.run(['su','-c','cat '+shlex.quote(str(path))],
                                  capture_output=True,timeout=35)
            return result.stdout if result.returncode==0 else None
        except (OSError,subprocess.TimeoutExpired):
            return None

def imports(raw):
    if not raw or len(raw)<64 or raw[:6]!=b'\x7fELF\x02\x01':
        return {}
    off=struct.unpack_from('<Q',raw,40)[0]
    size,count,names_id=struct.unpack_from('<HHH',raw,58)
    if size!=64 or not count or names_id>=count or off+count*size>len(raw):
        return {}
    headers=[struct.unpack_from('<IIQQQQIIQQ',raw,off+i*size) for i in range(count)]
    n=headers[names_id]
    if n[4]+n[5]>len(raw):return {}
    names=raw[n[4]:n[4]+n[5]]
    for h in headers:
        if h[0]>=len(names) or names[h[0]:].split(b'\0',1)[0]!=b'__versions':
            continue
        if h[4]+h[5]>len(raw):return {}
        block=raw[h[4]:h[4]+h[5]]
        if len(block)%64:return {}
        return {block[i+8:i+64].split(b'\0',1)[0].decode('ascii','replace'):
                struct.unpack_from('<I',block,i)[0]
                for i in range(0,len(block),64) if block[i+8]!=0}
    return {}

def scan(directories,wanted):
    found=defaultdict(list)
    for directory in directories:
        if not os.path.isdir(directory):continue
        for base,_,filenames in os.walk(directory):
            for filename in filenames:
                if filename.endswith('.ko'):
                    module=filename[:-3].replace('-','_')
                    if module in wanted:
                        found[module].append(Path(base,filename))
    return found

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path('nevada-live-core-kmi.json'))
    parser.add_argument('--offline-dir',type=Path,
                        help='QA only: use all modules in a local directory')
    args=parser.parse_args()
    with args.manifest.open() as file:
        lines=list(csv.DictReader(file,delimiter='\t'))
    crc={row['symbol']:int(row['crc'],16) for row in lines}
    if len(lines)!=101 or len(crc)!=101 or 'usb_submit_urb' not in crc:
        raise SystemExit('Refusing invalid/incomplete 101-symbol CRC manifest')
    if args.offline_dir:
        directories=[str(args.offline_dir)]
        wanted={p.stem.replace('-','_') for p in args.offline_dir.rglob('*.ko')}
        mode='offline_recovery_fixture';kernel='offline'
    else:
        loaded=read('/proc/modules')
        if not loaded:
            raise SystemExit('Cannot read /proc/modules; KernelSU root read access may be required')
        wanted={line.split()[0].decode().replace('-','_')
                for line in loaded.splitlines() if line.split()}
        directories=STOCK_DIRS
        mode='normal_boot';kernel=os.uname().release
    found=scan(directories,wanted)
    matched=defaultdict(list);conflicted=defaultdict(list)
    examined=0;ambiguities=[];unreadable=[];missing_files=0
    for module in sorted(wanted):
        paths=found.get(module,[])
        if not paths:
            missing_files+=1
            continue
        if len(paths)!=1:
            ambiguities.append(module)
            continue
        raw=read(paths[0])
        if not raw:
            unreadable.append(module)
            continue
        examined+=1
        for symbol,value in imports(raw).items():
            if symbol not in crc:continue
            (matched if value==crc[symbol] else conflicted)[symbol].append({
                'stock_module':module,'import_crc':f'0x{value:08x}'})
    remaining=sorted(set(crc)-set(matched)-set(conflicted))
    # The exact official GKI build 14563692 lacks two Atheros imports.
    # /proc/kallsyms can sometimes expose whether the *running* device
    # retains these export names; do NOT interpret symbol values as CRCs
    # or log kernel addresses from this sensitive interface.
    core_export_names={
        'rfkill_pause_polling':'unavailable',
        'usb_get_urb':'unavailable',
        'kallsyms_exports_visible':False,
    }
    if mode=='normal_boot':
        kallsyms=read('/proc/kallsyms')
        if kallsyms:
            names={line.split()[2].decode('ascii','replace') for line
                   in kallsyms.splitlines() if len(line.split())>=3}
            visible=any(s.startswith('__ksymtab_') for s in names)
            core_export_names['kallsyms_exports_visible']=visible
            for sym in ('rfkill_pause_polling','usb_get_urb'):
                if visible:
                    core_export_names[sym]=('export_name_present' if
                          '__ksymtab_'+sym in names else 'not_seen_in_kallsyms')
    signature=None
    if mode=='normal_boot':
        for path in ('/sys/module/module/parameters/sig_enforce',
                     '/proc/sys/kernel/module_sig_enforce'):
            value=read(path)
            if value is not None:
                signature={'path':path,'value':value.decode(errors='replace').strip()}
                break
    report={
        'status':'READ-ONLY EVIDENCE; NOT INSTALLABLE',
        'mode':mode,'timestamp_utc':datetime.now(timezone.utc).isoformat(),
        'kernel_release':kernel,'experimental_vermagic':CANDIDATE_VERMAGIC,
        'required_unique_core_symbols':len(crc),
        'matching_symbol_witnesses':len(matched),
        'conflicting_symbol_witnesses':len(conflicted),
        'without_witness_symbols':len(remaining),
        'matching_import_witness_entries':sum(map(len,matched.values())),
        'conflicting_import_witness_entries':sum(map(len,conflicted.values())),
        'no_witness_symbols':remaining,
        'conflicts':dict(conflicted),'witnesses':dict(matched),
        'loaded_module_names':len(wanted),'module_ELFs_read':examined,
        'module_files_not_found':missing_files,
        'ambiguous_module_names':ambiguities,'unreadable_module_names':unreadable,
        'module_signature_enforcement':signature,
        'core_export_name_visibility':core_export_names,
        'limitations':('Working stock module imports corroborate candidate CRCs but '
                       'are not live vmlinux exports. 101/101 would still not prove '
                       'module loader signing, CFI, target vermagic, USB/OTG or firmware '
                       'compatibility. No module load, patch or flash was performed.')
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print('MOTO XT2615-1 READ-ONLY CORE ABI WITNESS | NOT INSTALLABLE')
    print('Kernel:',kernel,'loaded ELF module files read:',examined)
    print(f'{len(matched)}/101 symbol matches; {len(conflicted)} conflicts; '
          f'{len(remaining)} without loaded-module witnesses')
    if remaining: print('Unwitnessed:',', '.join(remaining))
    if conflicted:print('Conflicts:',json.dumps(dict(conflicted)))
    print('Candidate vermagic:',CANDIDATE_VERMAGIC)
    print('Module signing enforcement:',signature)
    print('Two GKI-missing export names in live kallsyms:',core_export_names)
    print('Report:',args.output)

if __name__=='__main__':main()

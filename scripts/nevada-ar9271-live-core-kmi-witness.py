#!/usr/bin/env python3
"""Motorola XT2615-1: READ-ONLY live-module ABI witness collection.

Compares experimental AR9271 core CRC requirements to the __versions imports
inside *already loaded* Android stock modules. A loaded module's import is
corroborating evidence, NOT an authoritative live kernel export CRC.
Does not insmod, patch, write kernel files, sign, or flash anything.
"""
import argparse, csv, hashlib, json, os, shlex, struct, subprocess
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

def scan_as_root(directories,wanted):
    """Enumerate ONLY .ko paths in known system module dirs using KernelSU.

    Ordinary Termux often cannot traverse vendor_dlkm directories, so an
    unprivileged os.walk() can silently return zero files. The optional root
    shell executes only read-only 'find', with shell-quoted fixed directories;
    its output is file paths, never module bytes or kernel addresses.
    """
    found=defaultdict(list)
    quoted=' '.join(shlex.quote(str(d)) for d in directories)
    command=(
        'for d in '+quoted+'; do '
        '[ -d "$d" ] || continue; '
        '(find -L "$d" -type f -name "*.ko" -print 2>/dev/null || '
        'find "$d" -type f -name "*.ko" -print 2>/dev/null); '
        'done'
    )
    try:
        result=subprocess.run(
            ['su','-c',command],capture_output=True,timeout=90,check=False
        )
    except (OSError,subprocess.TimeoutExpired) as e:
        return found,{'status':type(e).__name__,'root_paths_listed':0}
    # The script itself never executes paths from find as shell commands.
    paths=[x for x in result.stdout.decode('utf-8','replace').splitlines()
           if x.endswith('.ko') and x.startswith('/')]
    for p in paths:
        filename=Path(p).name
        module=filename[:-3].replace('-','_')
        if module in wanted:
            found[module].append(Path(p))
    status='ok' if result.returncode==0 else 'nonzero_exit'
    return found,{'status':status,'root_paths_listed':len(paths),
                  'root_loaded_name_matches':sum(len(x) for x in found.values())}



def elf_gnu_build_id_note(raw):
    """Get the raw .note.gnu.build-id section for comparison with sysfs.

    Raw note bytes (rather than an ELF pointer or kernel address) can be
    compared directly with /sys/module/<name>/notes/.note.gnu.build-id.
    Return None if metadata is missing or malformed. Read-only.
    """
    if not raw or len(raw)<64 or raw[:6]!=b'\x7fELF\x02\x01':
        return None
    try:
        off=struct.unpack_from('<Q',raw,40)[0]
        size,count,names_id=struct.unpack_from('<HHH',raw,58)
        if size!=64 or not count or names_id>=count or off+count*size>len(raw):
            return None
        hdrs=[struct.unpack_from('<IIQQQQIIQQ',raw,off+i*size)
              for i in range(count)]
        names_hdr=hdrs[names_id]
        begin=names_hdr[4]
        if begin+names_hdr[5]>len(raw):
            return None
        names=raw[begin:begin+names_hdr[5]]
        for hdr in hdrs:
            if hdr[0]>=len(names):
                continue
            if names[hdr[0]:].split(b'\0',1)[0]!=b'.note.gnu.build-id':
                continue
            begin=hdr[4]
            if begin+hdr[5]>len(raw):
                return None
            note=raw[begin:begin+hdr[5]]
            return note or None
    except (ValueError,struct.error,IndexError):
        return None
    return None


def resolve_candidate(module, paths, mode):
    """Choose a stock ELF only when evidence identifies the same binary.

    Repeated mount paths are common on Android. If candidate bytes match
    SHA256, they're one physical ABI witness regardless of mount aliases.
    When bytes differ, select only a unique matching live GNU Build-ID.
    Never pick the first arbitrary .ko with the same filename.
    """
    groups={}
    unreadable=0
    for path in paths:
        raw=read(path)
        if not raw:
            unreadable+=1
            continue
        digest=hashlib.sha256(raw).hexdigest()
        if digest not in groups:
            groups[digest]=raw
    if not groups:
        return None,'unreadable',len(groups),unreadable
    live_note=(read('/sys/module/'+module+'/notes/.note.gnu.build-id')
               if mode=='normal_boot' else None)
    if live_note:
        matches=[raw for raw in groups.values()
                 if elf_gnu_build_id_note(raw)==live_note]
        if len(matches)==1:
            reason=('build_id_verified_unique' if len(groups)>1
                    else 'build_id_verified')
            return matches[0],reason,len(groups),unreadable
        if len(matches)==0:
            return None,'live_build_id_not_matched',len(groups),unreadable
        return None,'multiple_build_id_matches',len(groups),unreadable
    if len(groups)==1:
        reason='identical_copies' if len(paths)>1 else 'single_candidate'
        return next(iter(groups.values())),reason,len(groups),unreadable
    return None,'different_content_candidates',len(groups),unreadable


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
    user_scan_matches=sum(len(v) for v in found.values())
    root_scan_info={'status':'not_needed_offline','root_paths_listed':0,
                    'root_loaded_name_matches':0}
    if mode=='normal_boot':
        from_root,root_scan_info=scan_as_root(directories,wanted)
        for name,paths in from_root.items():
            # The same stock module can be visible through bind mounts,
            # symlinks or both scans; deduplicate canonical paths first.
            prior={os.path.realpath(str(p)) for p in found[name]}
            for p in paths:
                canonical=os.path.realpath(str(p))
                if canonical not in prior:
                    found[name].append(p)
                    prior.add(canonical)
    matched=defaultdict(list);conflicted=defaultdict(list)
    examined=0;ambiguities=[];unreadable=[];missing_files=0
    duplicate_groups_resolved=0;build_ids_verified=0
    selection_reasons=defaultdict(int)
    for module in sorted(wanted):
        paths=found.get(module,[])
        if not paths:
            missing_files+=1
            selection_reasons['no_module_file_found']+=1
            continue
        raw,reason,unique_contents,unreadable_paths=resolve_candidate(
            module,paths,mode)
        selection_reasons[reason]+=1
        if raw is None:
            if reason=='unreadable':
                unreadable.append(module)
            else:
                ambiguities.append(module)
            continue
        if reason=='identical_copies':
            duplicate_groups_resolved+=1
        if reason.startswith('build_id_verified'):
            build_ids_verified+=1
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
        'unprivileged_module_path_matches':user_scan_matches,
        'root_module_path_enumeration':root_scan_info,
        'module_selection_reasons':dict(sorted(selection_reasons.items())),
        'identical_duplicate_groups_resolved':duplicate_groups_resolved,
        'matching_live_build_ids_verified':build_ids_verified,
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
    print('Module path discovery: unprivileged matches:',user_scan_matches,
          '| rooted find:',root_scan_info)
    print('Module selection:',dict(sorted(selection_reasons.items())),
          '| duplicate groups resolved:',duplicate_groups_resolved,
          '| matched live Build-IDs:',build_ids_verified)
    if mode=='normal_boot' and not examined:
        print('INCOMPLETE: no loaded module ELF files could be selected or read;'
              ' examine module selection reasons, NOT 101 CRC incompatibilities.')
        print('No module was loaded.')
    print(f'{len(matched)}/101 symbol matches; {len(conflicted)} conflicts; '
          f'{len(remaining)} without loaded-module witnesses')
    if remaining: print('Unwitnessed:',', '.join(remaining))
    if conflicted:print('Conflicts:',json.dumps(dict(conflicted)))
    print('Candidate vermagic:',CANDIDATE_VERMAGIC)
    print('Module signing enforcement:',signature)
    print('Two GKI-missing export names in live kallsyms:',core_export_names)
    print('Report:',args.output)

if __name__=='__main__':main()

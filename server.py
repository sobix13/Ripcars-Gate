"""Scoped server provisioning. Unknown and externally edited resources are protected."""
from __future__ import annotations
import copy
import discord
import core
from db import Conflict

STAFF = ("moderator","admin","team")

def bits(**values):return discord.PermissionOverwrite(**values)
def overwrites(guild, roles, spec):
    policy=core.access_policy(spec)
    result={guild.default_role:bits(**policy["public"])}
    if roles.get("rippers"):
        result[roles["rippers"]]=bits(**policy["rippers"])
    if roles.get("og"):
        # OG is an additional access role. It does not replace onboarding.
        result[roles["og"]]=bits(**policy["og"])
    for key in STAFF:
        if roles.get(key):result[roles[key]]=bits(**policy["staff"])
    result[guild.me]=bits(**policy["bot"])
    return result

def role_snapshot(role):return dict(name=role.name,color=role.colour.value,permissions=role.permissions.value)

def channel_snapshot(ch, desired):
    result={"name":ch.name}
    if "parent" in desired:result["parent"]=ch.category_id
    if "topic" in desired:result["topic"]=ch.topic or ""
    if "slowmode" in desired:result["slowmode"]=ch.slowmode_delay
    if "kind" in desired:result["kind"]=str(ch.type)
    result["overwrites"]={}
    for target_id,flags in desired.get("overwrites",{}).items():
        target=ch.guild.get_role(int(target_id)) or ch.guild.get_member(int(target_id))
        if not target:
            result["overwrites"][target_id]={k:None for k in flags};continue
        ow=ch.overwrites_for(target)
        result["overwrites"][target_id]={k:getattr(ow,k) for k in flags}
    return result

def channel_desired(guild,roles,spec,parent):
    ow=overwrites(guild,roles,spec)
    d=dict(name=spec["name"],kind={"text":"text","category":"category","forum":"forum"}[spec["kind"]],
           overwrites={str(target.id):{k:v for k,v in value if v is not None} for target,value in ow.items()})
    if spec["kind"]!="category":
        d.update(parent=parent.id if parent else None,topic=spec["topic"],slowmode=0 if spec["mode"]=="submit" else min(spec["slowmode"],21600))
    return d

class Provisioner:
    def __init__(self,bot):self.bot=bot;self.db=bot.db;self.busy=set()
    async def plan(self,guild):
        cfg,_=await self.db.config(guild.id);res=await self.db.resources(guild.id);lines=[]
        for key,(name,_) in core.ROLE_SPECS.items():
            rk="role:"+key;name=cfg["claims"].get(key[6:],name) if key.startswith("claim_") else cfg["role_names"][key]
            r=res.get(rk);obj=guild.get_role(r["object_id"]) if r else None
            lines.append(f"{rk}: {'check existing ID' if obj else 'missing registered ID; review' if r else 'name conflict; bind ID' if any(x.name==name for x in guild.roles) else 'create'}")
        for key,spec in cfg["blueprint"].items():
            r=res.get("channel:"+key);obj=guild.get_channel(r["object_id"]) if r else None
            lines.append(f"{spec['name']}: {'check existing ID' if obj else 'missing registered ID; review' if r else 'name conflict; bind ID' if any(x.name==spec['name'] for x in guild.channels) else 'create'}")
        return lines
    async def apply(self,guild,actor,automatic=False):
        token=await self.db.lease(guild.id,"server-setup");results=[];created=set()
        self.busy.add(guild.id)
        try:
            cfg,_=await self.db.config(guild.id)
            core.validate(cfg)
            for key,(base_name,flags) in core.ROLE_SPECS.items():
                await self.db.renew(guild.id,"server-setup",token)
                name=cfg["claims"].get(key[6:],base_name) if key.startswith("claim_") else cfg["role_names"][key]
                desired=dict(name=name,color=cfg["color"],permissions=discord.Permissions(**{f:True for f in flags}).value)
                res=await self.db.resources(guild.id);rk="role:"+key;r=res.get(rk)
                try:
                    if r:
                        role=guild.get_role(r["object_id"])
                        if not role:await self.db.state(guild.id,rk,"missing");results.append(f"REVIEW {name}: registered role was deleted");continue
                        if r["owner"]!=core.OWNER or r["state"]!="active":results.append(f"PROTECTED {name}");continue
                        actual=role_snapshot(role)
                        if actual!=r["baseline"]:await self.db.state(guild.id,rk,"manual");results.append(f"MANUAL {name}: external change preserved");continue
                        if actual!=desired:
                            await role.edit(name=name,colour=discord.Colour(cfg["color"]),permissions=discord.Permissions(desired["permissions"]),reason="Ripcars Gate: managed role update")
                        await self.db.register(guild.id,rk,role.id,"role",desired,desired)
                    else:
                        if automatic:continue
                        if any(x.name==name for x in guild.roles):results.append(f"CONFLICT {name}: bind its ID in Resources");continue
                        role=await guild.create_role(name=name,colour=discord.Colour(cfg["color"]),permissions=discord.Permissions(desired["permissions"]),reason="Ripcars Gate: initial setup")
                        await self.db.register(guild.id,rk,role.id,"role",desired,desired)
                        created.add(key)
                    results.append(f"OK {name}")
                except discord.HTTPException as exc:results.append(f"FAILED {name}: {exc}")
            res=await self.db.resources(guild.id)
            roles={k:guild.get_role(res.get("role:"+k,{}).get("object_id",0)) for k in core.ROLE_SPECS}
            if not all(roles.get(k) for k in ("rippers","og",*STAFF)):
                results.append("BLOCKED: finish role setup before creating channels");return results
            # Existing role positions are intentionally preserved.
            if created==set(core.ROLE_SPECS):
                order=["claim_collectors","claim_updates","claim_announcements","claim_game","rippers","og","moderator","admin","team"]
                if all(roles[k]<guild.me.top_role for k in order):
                    positions=sorted(roles[k].position for k in order)
                    await guild.edit_role_positions(positions={roles[k]:p for k,p in zip(order,positions)},reason="Ripcars Gate: initial role hierarchy")
            for key,spec in cfg["blueprint"].items():
                await self.db.renew(guild.id,"server-setup",token)
                res=await self.db.resources(guild.id);rk="channel:"+key;r=res.get(rk)
                parent_row=res.get("channel:"+str(spec["parent"]));parent=guild.get_channel(parent_row["object_id"]) if parent_row else None
                if spec["parent"] and not parent:results.append(f"BLOCKED {spec['name']}: parent is missing");continue
                desired=channel_desired(guild,roles,spec,parent)
                try:
                    if r:
                        ch=guild.get_channel(r["object_id"])
                        if not ch:await self.db.state(guild.id,rk,"missing");results.append(f"REVIEW {spec['name']}: registered channel was deleted");continue
                        if r["owner"]!=core.OWNER or r["state"]!="active":results.append(f"PROTECTED {spec['name']}");continue
                        actual=channel_snapshot(ch,r["baseline"])
                        if actual!=r["baseline"]:await self.db.state(guild.id,rk,"manual");results.append(f"MANUAL {spec['name']}: external change preserved");continue
                        if str(ch.type)!=desired["kind"]:results.append(f"REVIEW {spec['name']}: type change requires a new channel or explicit binding");continue
                        if actual!=desired:
                            edit=dict(name=spec["name"],reason="Ripcars Gate: managed template update")
                            if spec["kind"]!="category":edit.update(category=parent,topic=spec["topic"],slowmode_delay=desired["slowmode"])
                            await ch.edit(**edit)
                            # Update only managed flags and retain every foreign overwrite.
                            for target,ow in overwrites(guild,roles,spec).items():
                                merged=ch.overwrites_for(target)
                                for flag,value in ow:
                                    if value is not None:setattr(merged,flag,value)
                                await ch.set_permissions(target,overwrite=merged,reason="Ripcars Gate: scoped access update")
                    else:
                        if automatic:continue
                        if any(x.name==spec["name"] for x in guild.channels):results.append(f"CONFLICT {spec['name']}: bind its ID in Resources");continue
                        args=dict(name=spec["name"],overwrites=overwrites(guild,roles,spec),reason="Ripcars Gate: initial setup")
                        if spec["kind"]=="category":ch=await guild.create_category(**args)
                        else:
                            args.update(category=parent,topic=spec["topic"],slowmode_delay=desired["slowmode"])
                            fn=guild.create_forum if spec["kind"]=="forum" else guild.create_text_channel
                            ch=await fn(**args)
                    await self.db.register(guild.id,rk,ch.id,spec["kind"],desired,desired)
                    results.append(f"OK {spec['name']}")
                except discord.HTTPException as exc:
                    if r:await self.db.state(guild.id,rk,"partial")
                    results.append(f"FAILED {spec['name']}: {exc}")
            res=await self.db.resources(guild.id)
            ops=res.get("channel:gate_log")
            if ops:
                current,revision=await self.db.config(guild.id)
                if current["ops_channel_id"] is None:
                    current["ops_channel_id"]=ops["object_id"];await self.db.save_config(guild.id,current,revision,actor)
            await self.db.log(guild.id,actor,"server_setup","\n".join(results))
            return results
        finally:
            self.busy.discard(guild.id)
            await self.db.release(guild.id,"server-setup",token)
    async def scan(self,guild):
        if guild.id in self.busy:return []
        changes=[]
        for key,r in (await self.db.resources(guild.id)).items():
            if r["owner"]!=core.OWNER or r["state"]!="active":continue
            obj=guild.get_role(r["object_id"]) if key.startswith("role:") else guild.get_channel(r["object_id"])
            if not obj:
                await self.db.state(guild.id,key,"missing");changes.append(key+": missing");continue
            actual=role_snapshot(obj) if key.startswith("role:") else channel_snapshot(obj,r["baseline"])
            if actual!=r["baseline"]:
                await self.db.state(guild.id,key,"manual");changes.append(key+": external change preserved")
        return changes

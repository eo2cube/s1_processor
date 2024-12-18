from .auxils import group_by_info
from spatialist.ancillary import finder
import os
from pathlib import Path
from .s1_coh_proc import S1_coh_proc
from .s1_h2a_proc import S1_HA_proc
from .s1_int_proc import S1_INT_proc


def S1_SLC_proc(
    data,
    maxdate=None,
    mindate=None,
   # shapefile=None,
    int_proc=False,
    coh_proc=False,
    ha_proc=False,
    INT_Test=False,
    outdir_int=None,
    outdir_coh=None,
    outdir_ha=None,
    INT_test_dir=None,
    tmpdir=None,
    res_int=20,
    res_coh=20,
    res_ha=20,
    t_crs=4326,
    out_format="GeoTIFF",
    gpt_paras=None,
    pol="full",
    iws=["IW1", "IW2", "IW3"],
    ext_dem=False,
    ext_dem_nodatval=-9999,
    ext_dem_file=None,
    msk_nodatval=False,
    ext_dem_egm=True,
    decompfeats=["Alpha", "Entropy", "Anisotropy"],
    ha_speckfilter="Box Car Filter",
    decomp_win_size=5,
    osvpath=None,
    imgresamp="BICUBIC_INTERPOLATION",
    demresamp="BILINEAR_INTERPOLATION",
    bgc_demresamp="BICUBIC_INTERPOLATION",
    tc_demresamp="BILINEAR_INTERPOLATION",
    cohwinrg=11,
    cohwinaz=3,
    speckfilter="Boxcar",
    filtersizex=5,
    filtersizey=5,
    ml_rglook=4,
    ml_azlook=1,
    l2db_arg=True,
    ref_plain="gamma",
    clean_tmpdir=True,
    osvfail=False,
    tmp_format="BEAM-DIMAP",
    slice_assembly=False,
):
    if tmpdir is not None:
        td = Path(tmpdir)
    else:
        tmpdir = os.path.join(os.getcwd(), "tmp_dir")
        td = Path(tmpdir)
    td.mkdir(parents=True, exist_ok=True)
    scenes = finder(
        data, [r"^S1[AB].*(.zip)$"], regex=True, recursive=True, foldermode=1
    )

    if int_proc is True:
        S1_INT_proc(
            infiles=scenes,
            out_dir=outdir_int,
            slice_assembly = slice_assembly,
            #shapefile=shapefile,
            t_res=res_int,
            tmpdir=tmpdir,
            t_crs=t_crs,
            out_format=out_format,
            gpt_paras=gpt_paras,
            pol=pol,
            IWs=iws,
            ext_DEM=ext_dem,
            ext_DEM_noDatVal=ext_dem_nodatval,
            ext_Dem_file=ext_dem_file,
            msk_noDatVal=msk_nodatval,
            ext_DEM_EGM=ext_dem_egm,
            imgResamp=imgresamp,
            demResamp=demresamp,
            speckFilter=speckfilter,
            osvPath=osvpath,
            ref_plain=ref_plain,
            filterSizeX=filtersizex,
            filterSizeY=filtersizey,
            ml_RgLook=ml_rglook,
            ml_AzLook=ml_azlook,
            l2dB_arg=l2db_arg,
            clean_tmpdir=clean_tmpdir,
            osvFail=osvfail,
            tpm_format=tmp_format,
        )
    if coh_proc is True:
        print("start sorting orbits")
        if isinstance(scenes, str):
            ##handling one file being passed down
            grp_by_orb = [scenes]
        else:
            ##group files by orbit: ascending/descending
            grp_by_orb = group_by_info(scenes, group="orbit")
            ##if only one orbit is detected
            if isinstance(grp_by_orb[0], str):
                grp_by_orb = [grp_by_orb]

        for orb in range(0, len(grp_by_orb)):
            ##handling one file being passed down
            if len(grp_by_orb) == 1 and isinstance(grp_by_orb[0], str):
                grp_by_relOrb = grp_by_orb
            else:
                ##group files by their relative orbit
                grp_by_relOrb = group_by_info(grp_by_orb[orb], group="orbitNumber_rel")
                ##if only one rel orbit is detected
                if isinstance(grp_by_relOrb[0], str):
                    grp_by_relOrb = [grp_by_relOrb]
            for ro in range(0, len(grp_by_relOrb)):
                S1_coh_proc(
                    infiles=grp_by_relOrb[ro],
                    out_dir=outdir_coh,
                   # shapefile=shapefile,
                    t_res=res_coh,
                    tmpdir=tmpdir,
                    t_crs=t_crs,
                    out_format=out_format,
                    gpt_paras=gpt_paras,
                    pol=pol,
                    IWs=iws,
                    ext_DEM=ext_dem,
                    ext_DEM_noDatVal=ext_dem_nodatval,
                    ext_Dem_file=ext_dem_file,
                    msk_noDatVal=msk_nodatval,
                    ext_DEM_EGM=ext_dem_egm,
                    BGC_demResamp=bgc_demresamp,
                    TC_demResamp=tc_demresamp,
                    cohWinRg=cohwinrg,
                    cohWinAz=cohwinaz,
                    osvPath=osvpath,
                    ml_RgLook=ml_rglook,
                    ml_AzLook=ml_azlook,
                    clean_tmpdir=clean_tmpdir,
                    osvFail=osvfail,
                    tpm_format=tmp_format,
                    slice_assembly=slice_assembly,
                )
    if ha_proc is True:
        for slc in scenes:
            S1_HA_proc(
                infiles=slc,
                out_dir=outdir_ha,
                shapefile=shapefile,
                t_res=res_ha,
                tmpdir=tmpdir,
                t_crs=t_crs,
                out_format=out_format,
                gpt_paras=gpt_paras,
                IWs=iws,
                ext_DEM=ext_dem,
                ext_DEM_noDatVal=ext_dem_nodatval,
                ext_Dem_file=ext_dem_file,
                msk_noDatVal=msk_nodatval,
                ext_DEM_EGM=ext_dem_egm,
                imgResamp=imgresamp,
                demResamp=demresamp,
                speckFilter=ha_speckfilter,
                decomp_win_size=decomp_win_size,
                decompFeats=decompfeats,
                ml_RgLook=ml_rglook,
                ml_AzLook=ml_azlook,
                osvPath=osvpath,
                osvFail=osvfail,
                clean_tmpdir=clean_tmpdir,
                tpm_format=tmp_format,
            )

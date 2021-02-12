var star_list = [];
var viz_calib = 0;
var viz_slew = false;
var slew_enabled = true;
var pending_select = null;

function get_draw_scale(zoom, scale_vert)
{
    var wrapdiv = document.getElementById("viewme");
    var imgw = wrapdiv.clientWidth;
    var imgh = Math.round((imgw / sensor_width) * sensor_height);
    var imgscale = sensor_width / imgw;

    // scale_vert will make the image fit to the vertical space
    if (scale_vert)
    {
        var reduce = 0;
        while (imgh > screen.height * 0.8) {
            reduce += 10;
            imgw = imgdiv.clientWidth - reduce;
            imgh = Math.round((imgw / sensor_width) * sensor_height);
            imgscale = sensor_width / imgw;
        }
    }

    // apply the zoom level
    imgscale /= zoom;
    return [sensor_width, sensor_height, imgw, imgh, imgscale];
}

function draw_guidescope(obj)
{
    if (obj === undefined || typeof obj === 'undefined') { if (last_status !== undefined && typeof last_status !== 'undefined') { obj = last_status; } else { return; } }
    if (obj == null) { if (last_status !== undefined && typeof last_status !== 'undefined') { obj = last_status; } else { return; } }
    //if (obj == null) { return ; }

    var wrapdiv = document.getElementById("viewme");
    var imgdiv = document.getElementById("viewmesvg");
    while (imgdiv.firstChild) {
        imgdiv.removeChild(imgdiv.firstChild);
    }

    var ds = get_draw_scale(1, false);
    var dataw    = ds[0];
    var datah    = ds[1];
    var imgw     = ds[2];
    var imgh     = ds[3];
    var imgscale = ds[4];
    var cent_x   = sensor_width  / 2 / imgscale;
    var cent_y   = sensor_height / 2 / imgscale;
    var offset_x = 0, offset_y = 0;

    // start the canvas with correct size
    var svgele = document.createElementNS(svgNS, "svg");
    //imgdiv.setAttribute("height", imgh);
    //imgdiv.style.height  = imgh + "px";
    imgdiv.style.top     = "-" + imgh + "px";
    wrapdiv.style.height = imgh + "px";
    svgele.setAttribute("id"    , "imgsvg");
    svgele.setAttribute("width" , imgw);
    svgele.setAttribute("height", imgh);
    svgele.setAttribute("xmlns" ,      "http://www.w3.org/2000/svg"  );
    svgele.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink");

    // draw a background rectangle that represents the background colour
    var bgrect = document.createElementNS(svgNS, "rect");
    bgrect.setAttribute("width", imgw);
    bgrect.setAttribute("height", imgh);
    bgrect.setAttribute("x", 0);
    bgrect.setAttribute("y", 0);
    var bgc = 0;
    if (obj != null) { Math.round(obj["img_mean"] * 0.9).toString(); }
    bgrect.setAttribute("style", "fill:rgb(" + bgc + "," + bgc + "," + bgc + ");stroke:none;");
    svgele.appendChild(bgrect);

    var need_parse_stars = false;
    if (star_list !== undefined && typeof star_list !== 'undefined') {
        if (star_list != null) {
            if (star_list.length <= 0) {
                need_parse_stars = true;
            }
        }
        else {
            need_parse_stars = true;
        }
    }
    else {
        need_parse_stars = true;
    }

    if (need_parse_stars && obj != null) {
        if (obj["stars"] != null && obj["stars"] != false) {
            star_list = parseStarsStr(obj["stars"]);
        }
    }

    var maxr = 0; // find the biggest star, used for other things later
    var minr = 9999;
    var maxscore = 0;
    var minscore = 9999;
    //var max_rating = 0;
    star_list.forEach(function(ele, idx) {
        if (ele["r"] > maxr) {
            maxr = ele["r"];
        }
        if (ele["r"] < minr) {
            minr = ele["r"];
        }
        if (ele["r"] > maxscore) {
            maxscore = ele["rating"];
        }
        if (ele["r"] < minscore) {
            minscore = ele["rating"];
        }
        //if (ele["r"] > max_rating) {
        //    max_rating = ele["rating"];
        //}
    });

    var cx, cy, cirele, lineele;

    if (selected_star !== undefined && typeof selected_star !== 'undefined')
    {
        if (selected_star != null) {
            cx = selected_star[0];
            cy = selected_star[1];
            var drawn_rad = math_mapStarRadius(maxr, minr, maxr, imgh) + 5;
            cirele = document.createElementNS(svgNS, "circle");
            cirele.setAttribute("cx", ((cx / imgscale) - offset_x).toFixed(8));
            cirele.setAttribute("cy", ((cy / imgscale) - offset_y).toFixed(8));
            cirele.setAttribute("r", drawn_rad);
            cirele.setAttribute("style", "stroke:rgb(32,255,32);stroke-width:1");
            svgele.appendChild(cirele);
        }
    }

    if (pending_select !== undefined && typeof pending_select !== 'undefined')
    {
        if (pending_select != null)
        {
            cx = pending_select[0];
            cy = pending_select[1];
            var drawn_rad = math_mapStarRadius(maxr, minr, maxr, imgh) + 7;
            cirele = document.createElementNS(svgNS, "circle");
            cirele.setAttribute("cx", ((cx / imgscale) - offset_x).toFixed(8));
            cirele.setAttribute("cy", ((cy / imgscale) - offset_y).toFixed(8));
            cirele.setAttribute("r", drawn_rad);
            cirele.setAttribute("style", "stroke:rgb(255,255,0);stroke-width:1");
            svgele.appendChild(cirele);
        }
    }

    // draw each star
    star_list.forEach(function(ele, idx) {
        cx = ele["cx"];
        cy = ele["cy"];
        var cpt = [cx / imgscale, cy / imgscale];

        var drawn_rad = math_mapStarRadius(ele["r"], minr, maxr, imgh);
        //cirele = document.createElementNS(svgNS, "circle");
        //cirele.setAttribute("cx", ((cx / imgscale) - offset_x).toFixed(8));
        //cirele.setAttribute("cy", ((cy / imgscale) - offset_y).toFixed(8));
        //cirele.setAttribute("r", drawn_rad);
        //cirele.setAttribute("style", "fill:rgb(" + get_star_color(ele) + ");stroke:none;");
        //svgele.appendChild(cirele);
        cirele = document.createElementNS(svgNS, "path");
        var pp1 = math_movePointTowards(cpt, [drawn_rad, 0]);
        var pp2 = math_movePointTowards(cpt, [drawn_rad, 0 + 180]);
        var pathstr = "M" + pp1[0] +  "," + pp1[1] + " " + "A" + drawn_rad + "," + drawn_rad + " 0 0 1 " + pp2[0] +  "," + pp2[1];
        cirele.setAttribute("d", pathstr);
        var rating_color = get_star_color(ele, math_mapVal(ele["rating"], minscore, maxscore, 0, 100));
        cirele.setAttribute("style", "fill:rgb(" + rating_color + ");stroke:none;");
        svgele.appendChild(cirele);
        cirele = document.createElementNS(svgNS, "path");
        pp1[1] += 0.5;
        pp2[1] += 0.5;
        pathstr = "M" + pp1[0] +  "," + pp1[1] + " " + "A" + drawn_rad + "," + drawn_rad + " 0 0 0 " + pp2[0] +  "," + pp2[1];
        cirele.setAttribute("d", pathstr);
        cirele.setAttribute("style", "fill:rgb(" + get_star_brightness(ele) + ");stroke:none;");
        svgele.appendChild(cirele);

        // draw one that's bigger so that it's easier to click
        // check distance to another nearby star to make sure we don't draw an overlapping clickable circle
        var mindist = -1;
        star_list.forEach(function(ele2, idx2) {
            if (idx == idx2) {
                return;
            }
            v = math_getVector([ele["cx"],ele["cy"]], [ele2["cx"],ele2["cy"]]);
            if (mindist < 0 || v[0] < mindist) {
                mindist = v[0];
            }
        });
        mindist = mindist / imgscale / 2;

        // establish minimum and maximum size of 
        if (mindist > drawn_rad)
        {
            drawn_rad = mindist;
            if (drawn_rad > imgh / 20) {
                drawn_rad = imgh / 20;
            }
            cirele = document.createElementNS(svgNS, "circle");
            cirele.setAttribute("cx", ((cx / imgscale) - offset_x).toFixed(8));
            cirele.setAttribute("cy", ((cy / imgscale) - offset_y).toFixed(8));
            cirele.setAttribute("r", drawn_rad);
            cirele.setAttribute("style", "fill:rgb(255,255,255, 0.001);stroke:none;");
            if (viz_slew == false) {
                cirele.setAttribute("onclick", "star_onclick(" + cx + ", " + cy + ");");
            }
            svgele.appendChild(cirele);
        }
    });

    if (tgt_coord !== undefined && typeof tgt_coord !== 'undefined')
    {
        if (tgt_coord != null)
        {
            var draw_tgt_coord = true;
            if (ori_coord !== undefined && typeof ori_coord !== 'undefined') {
                if (ori_coord != null) {
                    if (ori_coord[0] == tgt_coord[0] && ori_coord[1] == tgt_coord[1]) {
                        draw_tgt_coord = false;
                    }
                }
            }
            if (draw_tgt_coord)
            {
                cx = tgt_coord[0];
                cy = tgt_coord[1];
                var drawn_rad = math_mapStarRadius(maxr, minr, maxr, imgh) + 15;
                lineele = document.createElementNS(svgNS, "line");
                lineele.setAttribute("x1", ((cx / imgscale) - drawn_rad).toFixed(8));
                lineele.setAttribute("y1", ((cy / imgscale) - drawn_rad).toFixed(8));
                lineele.setAttribute("x2", ((cx / imgscale) + drawn_rad).toFixed(8));
                lineele.setAttribute("y2", ((cy / imgscale) + drawn_rad).toFixed(8));
                lineele.setAttribute("style", "stroke:rgb(64,64,255);stroke-width:1");
                svgele.appendChild(lineele);
                lineele = document.createElementNS(svgNS, "line");
                lineele.setAttribute("x1", ((cx / imgscale) + drawn_rad).toFixed(8));
                lineele.setAttribute("y1", ((cy / imgscale) - drawn_rad).toFixed(8));
                lineele.setAttribute("x2", ((cx / imgscale) - drawn_rad).toFixed(8));
                lineele.setAttribute("y2", ((cy / imgscale) + drawn_rad).toFixed(8));
                lineele.setAttribute("style", "stroke:rgb(64,64,255);stroke-width:1");
                svgele.appendChild(lineele);
            }
        }
    }

    if (ori_coord !== undefined && typeof ori_coord !== 'undefined')
    {
        if (ori_coord != null)
        {
            cx = ori_coord[0];
            cy = ori_coord[1];
            var drawn_rad = math_mapStarRadius(maxr, minr, maxr, imgh) + 20;
            lineele = document.createElementNS(svgNS, "line");
            lineele.setAttribute("x1", ((cx / imgscale) - drawn_rad).toFixed(8));
            lineele.setAttribute("y1", ((cy / imgscale)).toFixed(8));
            lineele.setAttribute("x2", ((cx / imgscale) + drawn_rad).toFixed(8));
            lineele.setAttribute("y2", ((cy / imgscale)).toFixed(8));
            lineele.setAttribute("style", "stroke:rgb(255,32,32);stroke-width:1");
            svgele.appendChild(lineele);
            lineele = document.createElementNS(svgNS, "line");
            lineele.setAttribute("x1", ((cx / imgscale)).toFixed(8));
            lineele.setAttribute("y1", ((cy / imgscale) - drawn_rad).toFixed(8));
            lineele.setAttribute("x2", ((cx / imgscale)).toFixed(8));
            lineele.setAttribute("y2", ((cy / imgscale) + drawn_rad).toFixed(8));
            lineele.setAttribute("style", "stroke:rgb(255,32,32);stroke-width:1");
            svgele.appendChild(lineele);
        }
    }

    var to_draw_calib = 0;

    if (viz_calib !== undefined && typeof viz_calib !== 'undefined') { to_draw_calib = viz_calib; }

    if (guide_state !== undefined && typeof guide_state !== 'undefined')
    {
        if (guide_state == 0)
        {
            var txtele; 
            txtele = document.createElementNS(svgNS, "text");
            txtele.setAttribute("x", 2);
            txtele.setAttribute("y", imgh - 5);
            if (star_list.length > 0 && viz_slew == false) {
                txtele.innerHTML = "click/touch star to change selection";
            }
            else if (viz_slew != false) {
                txtele.innerHTML = "click/touch red squares to issue test pulse";
            }
            else {
                txtele.innerHTML = "no stars detected";
            }
            txtele.setAttribute("style", "font-size:12pt;fill:rgb(255,255,128)");
            svgele.appendChild(txtele);
        }
    }

    if (to_draw_calib == 1) {
        draw_calibration(svgele, ds, obj, "ra");
    }
    else if (to_draw_calib == 2) {
        draw_calibration(svgele, ds, obj, "dec");
    }
    else if (to_draw_calib == 3) {
        draw_calibration(svgele, ds, obj, null);
    }
    else if (to_draw_calib == true) {
        draw_calibration(svgele, ds, obj, null);
    }

    if (viz_slew != false) {
        draw_slewcontrols(svgele, ds);
    }

    imgdiv.appendChild(svgele);
}

function get_star_color(star, rating)
{
    var s = 1;
    var v = star["max_brite"] / 255.0;
    if (v < 0.5) { v = 0.5; }
    var h = rating * 120 / 100 / 360;
    var rgb = hsv_2_rgb(h, s, v);
    return rgb.r.toString() + "," + rgb.g.toString() + "," + rgb.b.toString();
}

function get_star_brightness(star)
{
    var s = 0;
    var v = star["max_brite"] / 255.0;
    var h = star["rating"] * 120 / 100 / 360;
    var rgb = hsv_2_rgb(h, s, v);
    return rgb.r.toString() + "," + rgb.g.toString() + "," + rgb.b.toString();
}

function draw_calibration(svgele, drawscale, obj, axis)
{
    if (axis == undefined || typeof axis == 'undefined') {
        draw_calibration(svgele, drawscale, obj, "ra");
        draw_calibration(svgele, drawscale, obj, "dec");
        return;
    }
    if (axis == null) {
        draw_calibration(svgele, drawscale, obj, "ra");
        draw_calibration(svgele, drawscale, obj, "dec");
        return;
    }
    if (obj == null) {
        return;
    }
    var mainkey = "calib_" + axis;
    if (((mainkey) in obj) == false) {
        return;
    }
    var calibobj = obj[mainkey];
    if (calibobj == null || calibobj == false) {
        return;
    }
    var dataw    = drawscale[0];
    var datah    = drawscale[1];
    var imgw     = drawscale[2];
    var imgh     = drawscale[3];
    var imgscale = drawscale[4];

    var color = "0,0,0";
    if (axis == "ra") {
        color = "255,16,16";
    }
    else if (axis == "dec") {
        color = "64,64,255";
    }

    var txtele; 
    txtele = document.createElementNS(svgNS, "text");
    txtele.setAttribute("x", 2);
    if (axis == "ra") {
        txtele.setAttribute("y", 20);
        txtele.innerHTML = "&mdash; R.A. calibration";
    }
    else if (axis == "dec") {
        txtele.setAttribute("y", 40);
        txtele.innerHTML = "&mdash; Dec. calibration";
    }
    if (calibobj["success"] == "wait") {
        txtele.innerHTML += " (in progress...)";
    }
    else if (calibobj["success"] == "init") {
        txtele.innerHTML += " (not started)";
    }
    else if (calibobj["success"] == "failed") {
        txtele.innerHTML += " (failed)";
    }
    txtele.setAttribute("style", "font-size:12pt;fill:rgb(" + color +")");
    svgele.appendChild(txtele);

    var coord, cirele, lineele;
    //coord = calibobj["start_coord"];
    coord = [calibobj["start_x"], calibobj["start_y"]];
    cirele = document.createElementNS(svgNS, "circle");
    cirele.setAttribute("cx", ((coord[0] / imgscale)).toFixed(8));
    cirele.setAttribute("cy", ((coord[1] / imgscale)).toFixed(8));
    cirele.setAttribute("r", 4);
    cirele.setAttribute("style", "fill:rgb(" + color + ");stroke:none;");
    svgele.appendChild(cirele);
    cirele = document.createElementNS(svgNS, "circle");
    cirele.setAttribute("cx", ((coord[0] / imgscale)).toFixed(8));
    cirele.setAttribute("cy", ((coord[1] / imgscale)).toFixed(8));
    cirele.setAttribute("r", 6);
    cirele.setAttribute("style", "stroke:rgb(" + color + ");fill:none;");
    svgele.appendChild(cirele);

    if (calibobj["success"] == "done")
    {
        var linelength_1 = calibobj["pulse_width"] * calibobj["pix_per_ms"];
        var linelength_2 = calibobj["pulse_width"] * calibobj["points_cnt"] * calibobj["pix_per_ms"];
        var end_coord_1 = math_movePointTowards(coord, [linelength_1, calibobj["angle"]]);
        var end_coord_2 = math_movePointTowards(coord, [linelength_2, calibobj["angle"]]);
        var end_coord_3 = math_movePointTowards(coord, [sensor_width * 2, calibobj["angle"]]);
        lineele = document.createElementNS(svgNS, "line");
        lineele.setAttribute("x1", ((coord[0]       / imgscale)).toFixed(8));
        lineele.setAttribute("y1", ((coord[1]       / imgscale)).toFixed(8));
        lineele.setAttribute("x2", ((end_coord_1[0] / imgscale)).toFixed(8));
        lineele.setAttribute("y2", ((end_coord_1[1] / imgscale)).toFixed(8));
        lineele.setAttribute("style", "stroke:rgb(" + color + ");stroke-width:2");
        svgele.appendChild(lineele);
        lineele = document.createElementNS(svgNS, "line");
        lineele.setAttribute("x1", ((end_coord_1[0] / imgscale)).toFixed(8));
        lineele.setAttribute("y1", ((end_coord_1[1] / imgscale)).toFixed(8));
        lineele.setAttribute("x2", ((end_coord_2[0] / imgscale)).toFixed(8));
        lineele.setAttribute("y2", ((end_coord_2[1] / imgscale)).toFixed(8));
        lineele.setAttribute("style", "stroke:rgb(" + color + ",0.8);stroke-width:1");
        svgele.appendChild(lineele);
        lineele = document.createElementNS(svgNS, "line");
        lineele.setAttribute("x1", ((end_coord_1[0] / imgscale)).toFixed(8));
        lineele.setAttribute("y1", ((end_coord_1[1] / imgscale)).toFixed(8));
        lineele.setAttribute("x2", ((end_coord_3[0] / imgscale)).toFixed(8));
        lineele.setAttribute("y2", ((end_coord_3[1] / imgscale)).toFixed(8));
        lineele.setAttribute("style", "stroke:rgb(" + color + ",0.2);stroke-width:1");
        svgele.appendChild(lineele);
    }

    if (("points" in calibobj) != false)
    {
        var points = calibobj["points"];
        if (points != null && points != false)
        {
            points.forEach(function (pt, ptidx) {
                coord = pt;
                cirele = document.createElementNS(svgNS, "circle");
                cirele.setAttribute("cx", ((coord[0] / imgscale)).toFixed(8));
                cirele.setAttribute("cy", ((coord[1] / imgscale)).toFixed(8));
                cirele.setAttribute("r", 2);
                cirele.setAttribute("style", "fill:rgb(" + color + ");stroke:none;");
                svgele.appendChild(cirele);
                cirele = document.createElementNS(svgNS, "circle");
                cirele.setAttribute("cx", ((coord[0] / imgscale)).toFixed(8));
                cirele.setAttribute("cy", ((coord[1] / imgscale)).toFixed(8));
                cirele.setAttribute("r", 4);
                cirele.setAttribute("style", "stroke:rgb(" + color + ");fill:none;");
                svgele.appendChild(cirele);
            });
        }
    }
}

function draw_slewcontrols(svg, ds)
{
    var dataw    = ds[0];
    var datah    = ds[1];
    var imgw     = ds[2];
    var imgh     = ds[3];
    var imgscale = ds[4];

    var sqsize = imgh / 4;
    var stylestr, fontstr;
    if (slew_enabled)
    {
        stylestr = "stroke:rgb(255,0,0,1);stroke-width:1;fill:rgb(255,0,0,0.2);";
        fontstr = "font-size:" + (sqsize / 3) +  "px;font-family:sans-serif;color:red;fill:red;stroke:red;";
    }
    else
    {
        stylestr = "stroke:rgb(32,32,32,1);stroke-width:1;fill:rgb(32,32,32,0.2);";
        fontstr = "font-size:" + (sqsize / 3) +  "px;font-family:sans-serif;color:#444;fill:#444;stroke:#444;";
    }

    var rectele = document.createElementNS(svgNS, "rect");
    rectele.setAttribute("x", (imgw / 2) - (sqsize / 2));
    rectele.setAttribute("y", (imgh / 2) - (sqsize / 2) - sqsize);
    rectele.setAttribute("width", sqsize);
    rectele.setAttribute("height", sqsize);
    rectele.setAttribute("style", stylestr);
    rectele.setAttribute("onclick", "slew_onclick(\"n\");");
    svg.appendChild(rectele);

    var textele = document.createElementNS(svgNS, "text");
    textele.setAttribute("dominant-baseline", "middle");
    textele.setAttribute("text-anchor", "middle");
    textele.setAttribute("x", (imgw / 2));
    textele.setAttribute("y", (imgh / 2) - sqsize);
    textele.setAttribute("style", fontstr);
    textele.setAttribute("onclick", "slew_onclick(\"n\");");
    textele.innerHTML = "N";
    svg.appendChild(textele);

    rectele = document.createElementNS(svgNS, "rect");
    rectele.setAttribute("x", (imgw / 2) - (sqsize / 2));
    rectele.setAttribute("y", (imgh / 2) + (sqsize / 2));
    rectele.setAttribute("width" , sqsize);
    rectele.setAttribute("height", sqsize);
    rectele.setAttribute("style" , stylestr);
    rectele.setAttribute("onclick", "slew_onclick(\"s\");");
    svg.appendChild(rectele);

    textele = document.createElementNS(svgNS, "text");
    textele.setAttribute("dominant-baseline", "middle");
    textele.setAttribute("text-anchor", "middle");
    textele.setAttribute("x", (imgw / 2));
    textele.setAttribute("y", (imgh / 2) + sqsize);
    textele.setAttribute("style", fontstr);
    textele.setAttribute("onclick", "slew_onclick(\"s\");");
    textele.innerHTML = "S";
    svg.appendChild(textele);

    rectele = document.createElementNS(svgNS, "rect");
    rectele.setAttribute("x", (imgw / 2) - (sqsize / 2) - sqsize);
    rectele.setAttribute("y", (imgh / 2) - (sqsize / 2));
    rectele.setAttribute("width" , sqsize);
    rectele.setAttribute("height", sqsize);
    rectele.setAttribute("style" , stylestr);
    rectele.setAttribute("onclick", "slew_onclick(\"w\");");
    svg.appendChild(rectele);

    textele = document.createElementNS(svgNS, "text");
    textele.setAttribute("dominant-baseline", "middle");
    textele.setAttribute("text-anchor", "middle");
    textele.setAttribute("x", (imgw / 2) - sqsize);
    textele.setAttribute("y", (imgh / 2));
    textele.setAttribute("style", fontstr);
    textele.setAttribute("onclick", "slew_onclick(\"w\");");
    textele.innerHTML = "W";
    svg.appendChild(textele);

    rectele = document.createElementNS(svgNS, "rect");
    rectele.setAttribute("x", (imgw / 2) + (sqsize / 2));
    rectele.setAttribute("y", (imgh / 2) - (sqsize / 2));
    rectele.setAttribute("width" , sqsize);
    rectele.setAttribute("height", sqsize);
    rectele.setAttribute("style" , stylestr);
    rectele.setAttribute("onclick", "slew_onclick(\"e\");");
    svg.appendChild(rectele);

    textele = document.createElementNS(svgNS, "text");
    textele.setAttribute("dominant-baseline", "middle");
    textele.setAttribute("text-anchor", "middle");
    textele.setAttribute("x", (imgw / 2) + sqsize);
    textele.setAttribute("y", (imgh / 2));
    textele.setAttribute("style", fontstr);
    textele.setAttribute("onclick", "slew_onclick(\"e\");");
    textele.innerHTML = "E";
    svg.appendChild(textele);
}